import asyncio
from threading import Thread

from decouple import config
from quart import Quart, request
from hexbytes import HexBytes
from web3 import Web3, HTTPProvider

from auction import AuctionHouse


def register_routes(app: Quart, ah: AuctionHouse):

    @app.route("/register", methods=["POST"])
    async def register() -> dict:
        """
        input: {"pubKey": 0x...}
        """

        data = await request.get_json()
        assert("pubKey" in data)
        pubKey = HexBytes(data["pubKey"])

        await ah.register(pubKey)

        return {}

    @app.route("/getStatus", methods=["GET"])
    async def get_status() -> dict:
        """
        input: {"pubKey": 0x...}
        """

        data = await request.get_json()
        assert("pubKey" in data)
        pubKey = HexBytes(data["pubKey"])

        res = await ah.get_status(pubKey)

        return res

    @app.route("/submitTx", methods=["POST"])
    async def submit_tx():
        """
        input: {"txRaw": "0xabcdef.."}
        """

        data = await request.get_json()
        assert("txRaw" in data)
        tx_raw = HexBytes(data["txRaw"])

        res = await ah.submit_tx(tx_raw)

        return res

    @app.route("/txPool", methods=["GET"])
    async def get_txpool() -> dict:
        """
        input: {"pubKey": 0x...}
        """

        data = await request.get_json()
        assert("pubKey" in data)
        pubKey = HexBytes(data["pubKey"])

        res = await ah.get_txpool(pubKey)

        return res

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
            HexBytes(data["pubKey"]), HexBytes(data["txHash"]), int(data["value"])
        )

        try:
            res = await ah.submit_bid(pubKey, txHash, value)
            return res
        except ValueError as e:
            return {"error": str(e)}

    @app.route("/results", methods=["GET"])
    async def get_results() -> dict:
        """
        input: {"pubKey": 0x...}
        """

        data = await request.get_json()
        assert("pubKey" in data)
        pubKey = HexBytes(data["pubKey"])

        res = await ah.get_results(pubKey)

        return res



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
