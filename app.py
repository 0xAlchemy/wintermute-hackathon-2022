import asyncio
from enum import Enum
from threading import Thread

from decouple import config
from hexbytes import HexBytes
from quart import Quart, request
from web3 import Web3, HTTPProvider
from web3.types import Wei

from auction import AuctionHouse

HTTP_ERROR = 500


def register_routes(app: Quart, ah: AuctionHouse):

    @app.route("/register", methods=["POST"])
    async def register() -> dict:
        """
        input: {"pubKey": 0x...}
        """

        data = await request.get_json()
        assert("pubKey" in data)
        pubKey = HexBytes(data["pubKey"])

        try:
            await ah.register(pubKey)
            return ""
        except Exception as e:
            return str(e), HTTP_ERROR

    @app.route("/status", methods=["GET"])
    async def get_status() -> dict:
        """
        input: {"pubKey": 0x...}
        """

        data = await request.get_json()
        assert("pubKey" in data)
        pubKey = HexBytes(data["pubKey"])

        try:
            res = await ah.get_status(pubKey)
            return res
        except Exception as e:
            return str(e), HTTP_ERROR


    @app.route("/submitTx", methods=["POST"])
    async def submit_tx():
        """
        input: {"rawTx": "0xabcdef.."}
        """

        data = await request.get_json()
        assert("rawTx" in data)
        raw_tx = HexBytes(data["rawTx"])

        try:
            await ah.submit_tx(raw_tx)
            return ""
        except Exception as e:
            return str(e), HTTP_ERROR

    @app.route("/txPool", methods=["GET"])
    async def get_txpool() -> dict:
        """
        input: {"pubKey": 0x...}
        """

        data = await request.get_json()
        assert("pubKey" in data)
        pubKey = HexBytes(data["pubKey"])

        try:
            res = await ah.get_txpool(pubKey)
            return res
        except Exception as e:
            return str(e), HTTP_ERROR

    @app.route("/submitBid", methods=["POST"])
    async def submit_bid() -> dict:
        """
        input: {"pubKey": 0x.., "txHash": 0x.., "value": int}
        """

        data = await request.get_json()

        assert(
            "pubKey" in data
            and "txHash" in data
            and "value" in data
        )
        pubKey, txHash, value = (
            HexBytes(data["pubKey"]), HexBytes(data["txHash"]), Wei(int(data["value"]))
        )

        try:
            res = await ah.submit_bid(pubKey, txHash, value)
            return res
        except ValueError as e:
            return str(e), HTTP_ERROR

    @app.route("/results", methods=["GET"])
    async def get_results() -> dict:
        """
        input: {"pubKey": 0x...}
        """

        data = await request.get_json()
        assert("pubKey" in data and "slot" in data)
        pubKey = HexBytes(data["pubKey"])
        slot = int(data["slot"])

        res = await ah.get_results(pubKey, slot)

        try:
            res = await ah.get_results(pubKey, slot)
            return res
        except Exception as e:
            return str(e), HTTP_ERROR


class AuctionThread(Thread):
    ah: AuctionHouse

    def __init__(self, ah: AuctionHouse) -> None:
        super().__init__()
        self.ah = ah
    
    def run(self):
        asyncio.run(self.ah.run_auction())


class CleanupThread(Thread):
    ah: AuctionHouse

    def __init__(self, ah: AuctionHouse) -> None:
        super().__init__()
        self.ah = ah
    
    def run(self):
        asyncio.run(self.ah.run_cleanup())


if __name__ == "__main__":
    w3 = Web3(HTTPProvider(config("PROVIDER")))
    ah = AuctionHouse(w3)

    at = AuctionThread(ah)
    ct = CleanupThread(ah)

    at.start()
    ct.start()

    app = Quart(__name__)
    register_routes(app, ah)
    app.run()
