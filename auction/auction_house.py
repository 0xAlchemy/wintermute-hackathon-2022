import asyncio
import copy
import time
from typing import NoReturn

from hexbytes import HexBytes
from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.types import TxData, Wei

from .auction import Auction
from .types import Bid, Builder, Result, Transaction
from .utils import encode_tx_data, decode_raw_tx

MIN_TIME_IN_TX_POOL = 1
MAX_SLOTS_IN_TX_POOL = 10


class AuctionHouse:
    w3: Web3
    beacon_genesis: int

    builders: dict[HexBytes, Builder]
    builder_lock: asyncio.Lock = asyncio.Lock()

    txpool: dict[HexBytes, Transaction]
    txpool_lock: asyncio.Lock = asyncio.Lock()

    auctions: dict[HexBytes, Auction]
    auction_lock: asyncio.Lock = asyncio.Lock()

    results: dict[int, list[tuple[Result, TxData]]]

    def __init__(self, w3: Web3, beacon_genesis: int) -> None:
        self.w3 = w3
        self.beacon_genesis = beacon_genesis

        self.builders = {}
        self.txpool = {}
        self.auctions = {}
        self.results = {}

    # =================== #
    # auction house logic #
    # =================== #

    async def run_auction(self) -> NoReturn:
        slot_number = 0
        while True:
            if (new_slot := self._get_current_slot()) <= slot_number:
                asyncio.sleep(0.1)
            slot_number = new_slot

            asyncio.sleep(10)
            await self.settle(slot_number)

    async def settle(self, slot_number: int) -> None:
        started = time.time()

        results = []
        postponed_auctions: dict[HexBytes, Auction] = {}
        with self.auction_lock, self.builder_lock, self.txpool_lock:
            for tx_hash, auction in self.auctions.items():
                tx = self._get_tx_by_hash(tx_hash)
                if tx.submitted >= started - MIN_TIME_IN_TX_POOL:
                    postponed_auctions[tx_hash] = auction
                    continue

                result = auction.settle()
                results.append((result, tx.data))
                self.txpool[tx_hash].sold = True
                self.builders[result.winner_pubkey].pending_payment += result.payment

            self.results[slot_number] = results
            self.auctions = postponed_auctions

    # ============= #
    # cleanup logic #
    # ============= #

    async def run_cleanup(self) -> NoReturn:
        block_number = 0
        while True:
            if (new_block := await self.w3.eth.block_number) <= block_number:
                asyncio.sleep(0.1)
            block_number = new_block

            await self.process_executed()
            await self.process_expired()

    async def process_executed(self) -> None:
        # remove executed transactions from txpool
        executed_txs = []
        for tx_hash in self.txpool:
            try:
                await self.w3.eth.get_transaction_receipt(tx_hash)
                executed_txs.append(tx_hash)
            except TransactionNotFound:
                pass
        with self.txpool_lock, self.auction_lock:
            for tx_hash in executed_txs:
                del self.txpool[tx_hash]
                if tx_hash in self.auctions:
                    del self.auctions[tx_hash]

    async def process_expired(self) -> None:
        # remove expired transactions from txpool and send to public mempool
        now = time.time()
        expired_txs = []
        for tx_hash, tx in self.txpool.items():
            if (now - tx.submitted) // 12 > MAX_SLOTS_IN_TX_POOL:
                await self.w3.eth.send_raw_transaction(encode_tx_data(tx.data))
                expired_txs.append(tx_hash)
        with self.txpool_lock, self.auction_lock:
            for tx_hash in expired_txs:
                del self.txpool[tx_hash]
                if tx_hash in self.auctions:
                    del self.auctions[tx_hash]

    # ================= #
    # storage I/O logic #
    # ================= #

    async def register(self, pubkey: HexBytes) -> None:
        """Register the builder in the system."""
        if pubkey in self.builders:
            raise ValueError("Already registered.")
        with self.builder_lock:
            # TODO: validate if pubkey is registered in flashbots boost relay
            self.builders[pubkey] = Builder(pubkey, True, 0)

    async def get_status(self, pubkey: HexBytes) -> dict:
        """Check builder's status."""
        builder = self._get_builder_by_pubkey(pubkey)
        return {"access": builder.access, "pending_payment": builder.pending_payment}

    async def submit_tx(self, raw_tx: HexBytes) -> None:
        submitted = time.time()
        tx_data = decode_raw_tx(raw_tx)
        tx_hash = tx_data["hash"]

        if tx_hash in self.txpool:
            raise ValueError("Already in txpool.")

        fee = tx_data["maxPriorityFeePerGas"]
        try:
            # TODO: check if that works
            gas = self.w3.eth.estimate_gas(tx_data)
        except:
            raise ValueError("Invalid transaction.")

        with self.txpool_lock:
            self.txpool[tx_hash] = Transaction(
                tx_hash,
                tx_data,
                Wei(fee * gas),
                submitted,
                False,
                False,
            )

    async def get_txpool(self, pubkey: HexBytes) -> list[TxData]:
        builder = self._get_builder_by_pubkey(pubkey)
        if not builder.access:
            raise ValueError("Access restricted.")
        
        txpool = []
        for _, tx in self.txpool.items():
            if tx.sold:
                continue
            tx_data = copy.copy(tx.data)
            tx_data["v"], tx_data["r"], tx_data["s"] = 0, HexBytes(""), HexBytes("")
            txpool.append(tx_data)
        return txpool

    async def submit_bid(
        self, pubkey: HexBytes, tx_hash: HexBytes, value: Wei
    ) -> None:
        submitted = time.time()

        builder = self._get_builder_by_pubkey(pubkey)
        if not builder.access:
            raise ValueError("Access restricted.")
        
        tx = self._get_tx_by_hash(tx_hash)
        if tx.sold:
            raise ValueError("Can't bid for this tx.")
        if value < tx.reserve:
            raise ValueError("Reserve price not met.")

        bid = Bid(pubkey, tx_hash, value, submitted)
        with self.auction_lock:
            if (auction := self.auctions.get(tx_hash)):
                auction.submit(bid)
            else:
                self.auctions[tx_hash] = Auction(tx, bid)

    async def get_results(self, pubkey: HexBytes, slot: int) -> dict:
        builder = self._get_builder_by_pubkey(pubkey)
        if not builder.access:
            raise ValueError("Access restricted.")

        if slot not in self.results:
            raise ValueError(f"No results for slot {slot}")

        total_payment = 0
        txs: dict = {}
        for res, tx_data in self.results[slot]:
            if res.winner_pubkey != pubkey:
                continue
            total_payment += res.payment
            txs[res.tx_hash] = {
                "payment": res.payment,
                "data": tx_data,
            }
        return {"transactions": txs, "total_payment": total_payment}

    # ========= #
    # internals #
    # ========= #

    def _get_current_slot(self) -> int:
        return int((time.time() - self.beacon_genesis) // 12)

    def _get_builder_by_pubkey(self, pubkey: HexBytes) -> Builder:
        if not (builder := self.builders.get(pubkey)):
            raise ValueError("Builder is not registered.")
        return builder

    def _get_tx_by_hash(self, tx_hash: HexBytes) -> Transaction:
        if not (tx := self.txpool.get(tx_hash)):
            raise ValueError("tx is not in the pool.")
        return tx
