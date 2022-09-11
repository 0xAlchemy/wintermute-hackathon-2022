from .types import Bid, Transaction, Result


class Auction:
    """Sealed-bid second-price auction with reserve price."""

    tx: Transaction
    """Auctioned transaction."""
    bids: list[Bid]
    """Submitted bids."""

    def __init__(self, tx: Transaction, bid: Bid) -> None:
        self.tx, self.bids = tx, []
        self.submit(bid)

    def submit(self, bid: Bid) -> None:
        self._validate_bid(bid)
        self.bids.append(bid)

    def settle(self) -> Result:
        if len(self.bids) == 1:
            return Result(self.bids[0].builder_pubkey, self.tx.hash, self.tx.reserve)
        sorted_bids = sorted(self.bids, key=lambda b: (b.value, -b.submitted), reverse=True)
        winning_bid, second_bid = sorted_bids[0], sorted_bids[1]
        return Result(winning_bid.builder_pubkey, self.tx.hash, second_bid.value)

    def _validate_bid(self, bid: Bid) -> None:
        if bid.tx_hash != self.tx.hash:
            raise ValueError("Bid for the wrong item.")
        if bid.value < self.tx.reserve:
            raise ValueError("Bid is below the reserve price.")
