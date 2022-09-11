from dataclasses import dataclass

from hexbytes import HexBytes
from web3.types import TxData, Wei


@dataclass
class Builder:
    pubkey: HexBytes
    access: bool
    pending_payment: Wei


@dataclass
class Transaction:
    hash: HexBytes
    data: TxData
    reserve: Wei
    submitted: float
    sold: bool
    executed: bool


@dataclass
class Bid:
    builder_pubkey: HexBytes
    tx_hash: HexBytes
    value: Wei
    submitted: float


@dataclass
class Result:
    winner_pubkey: HexBytes
    tx_hash: HexBytes
    payment: Wei
