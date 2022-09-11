import rlp
from eth_account import Account
from eth_account._utils.legacy_transactions import (
    Transaction,
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_account._utils.typed_transactions import (
    AccessListTransaction,
    DynamicFeeTransaction,
)
from hexbytes import HexBytes
from web3 import Web3
from web3.types import TxData


def encode_tx_data(tx_data: TxData) -> HexBytes:
    """Encode transaction dict from the mempool, return the raw transaction."""
    v, r, s = (
        tx_data["v"],
        int(tx_data["r"].hex(), base=16),
        int(tx_data["s"].hex(), base=16),
    )

    tx_dict = {
        "nonce": tx_data["nonce"],
        "data": HexBytes(tx_data["input"]),
        "value": tx_data["value"],
        "gas": tx_data["gas"],
    }

    if "maxFeePerGas" in tx_data or "maxPriorityFeePerGas" in tx_data:
        assert "maxFeePerGas" in tx_data and "maxPriorityFeePerGas" in tx_data
        tx_dict["maxFeePerGas"], tx_dict["maxPriorityFeePerGas"] = (
            tx_data["maxFeePerGas"],
            tx_data["maxPriorityFeePerGas"],
        )
    else:
        assert "gasPrice" in tx_data
        tx_dict["gasPrice"] = tx_data["gasPrice"]

    if tx_data.get("accessList"):
        tx_dict["accessList"] = tx_data["accessList"]

    if tx_data.get("chainId"):
        tx_dict["chainId"] = tx_data["chainId"]

    if tx_data.get("to"):
        tx_dict["to"] = HexBytes(tx_data["to"])

    unsigned_tx = serializable_unsigned_transaction_from_dict(tx_dict)
    raw_tx = encode_transaction(unsigned_tx, vrs=(v, r, s))
    assert Web3.keccak(raw_tx) == tx_data["hash"]
    return HexBytes(raw_tx)


def decode_raw_tx(raw_tx: HexBytes) -> TxData:
    """Decode raw signed transaction."""
    # decode tx params based on its type
    tx_type = raw_tx[0]
    if tx_type > int("0x7f", 16):
        # legacy and EIP-155 transactions
        tx_data = rlp.decode(raw_tx, Transaction).as_dict()
    else:
        # typed transactions (EIP-2718)
        if tx_type == 1:
            # EIP-2930
            sedes = AccessListTransaction._signed_transaction_serializer
        elif tx_type == 2:
            # EIP-1559
            sedes = DynamicFeeTransaction._signed_transaction_serializer
        else:
            raise ValueError(f"Unknown transaction type: {tx_type}.")
        tx_data = rlp.decode(raw_tx[1:], sedes).as_dict()

    # recover sender address and remove signature fields
    tx_data["from"] = Account.recover_transaction(raw_tx)
    tx_data["data"] = HexBytes(tx_data["data"])
    return tx_data
