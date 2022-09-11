from quart import Quart, request
from hexbytes import HexBytes

class AuctionHouse:
    def __init__(self) -> None:
        pass

    async def get_tx_pool(self, pubKey: HexBytes) -> dict:
        return {"txPool": []}

    async def submit_bid(self, pubKey: HexBytes, txHash: HexBytes, value: int) -> dict:
        return {"status": True}

    async def results(self, pubKey: HexBytes) -> dict:
        return {"results": []}
    
    async def register(self, pubKey: HexBytes) -> dict:
        return {"status": True}
    
    async def get_status(self, pubkey: HexBytes) -> dict:
        return {"status": True}
    
    async def submit_tx(self, tx_raw: HexBytes) -> dict:
        return {"status": True}


def register_routes(app: Quart, ah: AuctionHouse):
    @app.route("/txPool", methods=["GET"])
    async def get_tx_pool() -> dict:
        """
        input: {"pubKey": 0x...}
        """

        data = await request.get_json()
        assert("pubKey" in data)
        pubKey = HexBytes(data["pubKey"])

        res = await ah.get_tx_pool(pubKey)

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
    async def results() -> dict:
        """
        input: {"pubKey": 0x...}
        """

        data = await request.get_json()
        assert("pubKey" in data)
        pubKey = HexBytes(data["pubKey"])

        res = await ah.results(pubKey)

        return res

    @app.route("/register", methods=["POST"])
    async def register() -> dict:
        """
        input: {"pubKey": 0x...}
        """

        data = await request.get_json()
        assert("pubKey" in data)
        pubKey = HexBytes(data["pubKey"])

        res = await ah.register(pubKey)

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


if __name__ == "__main__":
    app = Quart(__name__)
    ah = AuctionHouse()

    register_routes(app, ah)
    app.run()
