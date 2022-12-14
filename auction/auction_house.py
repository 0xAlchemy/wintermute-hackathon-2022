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

GENESIS_TIME = 1606824023
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

    def __init__(self, w3: Web3) -> None:
        self.w3 = w3

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
                await asyncio.sleep(0.1)
                continue
            slot_number = new_slot

            await asyncio.sleep(10)
            await self.settle(slot_number)

    async def settle(self, slot_number: int) -> None:
        started = time.time()

        results = []
        postponed_auctions: dict[HexBytes, Auction] = {}
        async with self.auction_lock, self.builder_lock, self.txpool_lock:
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
            if (new_block := self.w3.eth.block_number) <= block_number:
                await asyncio.sleep(0.1)
                continue
            block_number = new_block

            await self.process_executed()
            await self.process_expired()

    async def process_executed(self) -> None:
        # remove executed transactions from txpool
        executed_txs = []
        for tx_hash in self.txpool:
            try:
                self.w3.eth.get_transaction_receipt(tx_hash)
                executed_txs.append(tx_hash)
            except TransactionNotFound:
                pass
        async with self.txpool_lock, self.auction_lock:
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
                self.w3.eth.send_raw_transaction(encode_tx_data(tx.data))
                expired_txs.append(tx_hash)
        async with self.txpool_lock, self.auction_lock:
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
        async with self.builder_lock:
            # TODO: validate if pubkey is registered in flashbots boost relay
            self.builders[pubkey] = Builder(pubkey, True, 0)

    async def get_status(self, pubkey: HexBytes) -> dict:
        """Check builder's status."""
        builder = self._get_builder_by_pubkey(pubkey)
        return {
            "access": builder.access,
            "pendingPayment": str(builder.pending_payment),
        }

    async def submit_tx(self, raw_tx: HexBytes) -> None:
        submitted = time.time()
        tx_data = decode_raw_tx(raw_tx)
        tx_hash = HexBytes(tx_data["hash"])

        if tx_hash in self.txpool:
            raise ValueError("Already in txpool.")

        fee = tx_data["maxPriorityFeePerGas"]
        try:
            gas = self.w3.eth.estimate_gas(tx_data)
        except:
            raise ValueError("Invalid transaction.")

        async with self.txpool_lock:
            self.txpool[tx_hash] = Transaction(
                tx_hash,
                tx_data,
                Wei(fee * gas),
                submitted,
                False,
                False,
            )

    async def get_txpool(self, pubkey: HexBytes) -> list[dict]:
        builder = self._get_builder_by_pubkey(pubkey)
        if not builder.access:
            raise ValueError("Access restricted.")
        
        txpool = []
        for _, tx in self.txpool.items():
            if tx.sold:
                continue
            tx_data = copy.copy(tx.data)
            tx_data["v"], tx_data["r"], tx_data["s"] = 0, "", ""
            txpool.append({
                "data": tx_data,
                "reserve": str(tx.reserve),
            })
        return txpool

    async def submit_bid(
        self, pubkey: HexBytes, tx_hash: HexBytes, value: Wei
    ) -> dict:
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
        async with self.auction_lock:
            if (auction := self.auctions.get(tx_hash)):
                auction.submit(bid)
            else:
                self.auctions[tx_hash] = Auction(tx, bid)
        slot = self._get_current_slot()
        if slot in self.results or submitted - tx.submitted < MIN_TIME_IN_TX_POOL:
            return {"slot": str(slot + 1)}
        else:
            return {"slot": str(slot)}

    async def get_results(self, pubkey: HexBytes, slot: int) -> list[dict]:
        builder = self._get_builder_by_pubkey(pubkey)
        if not builder.access:
            raise ValueError("Access restricted.")

        if slot not in self.results:
            return {"transactions": [], "total_payment": "0"}

        total_payment = 0
        txs: list = []
        for res, tx_data in self.results[slot]:
            if res.winner_pubkey != pubkey:
                continue
            total_payment += res.payment
            txs.append({
                "payment": str(res.payment),
                "data": tx_data,
            })
        return {"transactions": txs, "total_payment": str(total_payment)}

    # ========= #
    # internals #
    # ========= #

    def _get_current_slot(self) -> int:
        return int((time.time() - GENESIS_TIME) // 12)

    def _get_builder_by_pubkey(self, pubkey: HexBytes) -> Builder:
        if not (builder := self.builders.get(pubkey)):
            raise ValueError("Builder is not registered.")
        return builder

    def _get_tx_by_hash(self, tx_hash: HexBytes) -> Transaction:
        if not (tx := self.txpool.get(tx_hash)):
            raise ValueError("tx is not in the pool.")
        return tx
