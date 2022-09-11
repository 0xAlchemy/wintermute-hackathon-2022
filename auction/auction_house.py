import asyncio
import copy
import time
from typing import NoReturn

from hexbytes import HexBytes
from web3 import Web3
from web3.beacon import Beacon
from web3.types import TxData, Wei

from .auction import Auction
from .types import Bid, Builder, Result, Transaction

MIN_TIME_IN_TX_POOL = 1

# TODO: add payments and access restriction
# TODO: add transaction execution check


class AuctionHouse:
    w3: Web3
    beacon: Beacon
    current_slot: int

    builders: dict[HexBytes, Builder] # pubkey -> Builder
    builder_lock: asyncio.Lock = asyncio.Lock()

    txpool: dict[HexBytes, Transaction] # hash -> Transaction
    txpool_lock: asyncio.Lock = asyncio.Lock()

    auctions: dict[HexBytes, Auction] # hash -> Auction
    auction_lock: asyncio.Lock = asyncio.Lock()

    results: dict[int, dict[HexBytes, Result]]

    def __init__(self, w3: Web3, beacon: Beacon) -> None:
        self.w3 = w3
        self.beacon = beacon
        self.current_slot = 0

        self.builders = {}
        self.txpool = {}
        self.auctions = {}
        self.results = {}

    # =================== #
    # auction house logic #
    # =================== #

    async def run(self) -> NoReturn:
        while True:
            if (new_slot := self._get_current_slot()) <= self.current_slot:
                asyncio.sleep(0.1)
            self.current_clot = new_slot

            asyncio.sleep(10)
            await self.settle()

    async def settle(self) -> None:
        started = time.time()
        postponed_auctions: dict[HexBytes, Auction] = {}
        with self.auction_lock, self.builder_lock, self.txpool_lock:
            for tx_hash, auction in self.auctions.items():
                tx = self._get_tx_by_hash(tx_hash)
                if tx.submitted >= started - MIN_TIME_IN_TX_POOL:
                    postponed_auctions[tx_hash] = auction
                    continue

                result = auction.settle()
                self.results[self.current_clot][tx_hash] = result
                self.txpool[tx_hash].sold = True
                self.builders[result.winner_pubkey].pending_payment += result.payment
            self.auctions = postponed_auctions

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

    async def submit_tx(self, tx_data: TxData) -> None:
        submitted = time.time()
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
            if tx.sold or tx.executed:
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
        if tx.sold or tx.executed:
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
        for tx_hash, res in self.results[slot].items():
            if res.winner_pubkey != pubkey:
                continue
            tx = self._get_tx_by_hash(tx_hash)
            total_payment += res.payment
            txs[tx_hash] = {
                "payment": res.payment,
                "data": tx.data,
            }
        return {"transactions": txs, "total_payment": total_payment}

    # ========= #
    # internals #
    # ========= #

    def _get_current_slot(self) -> int:
        # TODO: this is some unstable garbage here but ok
        return self.beacon.get_block_headers()["data"][0]["header"]["message"]["slot"]

    def _get_builder_by_pubkey(self, pubkey: HexBytes) -> Builder:
        if not (builder := self.builders.get(pubkey)):
            raise ValueError("Builder is not registered.")
        return builder

    def _get_tx_by_hash(self, tx_hash: HexBytes) -> Transaction:
        if not (tx := self.txpool.get(tx_hash)):
            raise ValueError("tx is not in the pool.")
        return tx
