# Order Flow Auction Relay

Private order flow has recently become a concern for Ethereum community as it is a strong centralizing factor for builders in PBS architecture. A good overview of this topic is given in [this](https://www.youtube.com/watch?v=ilc3EoSMMDg) SBC 2022 talk by [0xQuintus](https://twitter.com/0xQuintus).

This project, made for [Encode x Wintermute MEV Hackathon](https://www.encode.club/wintermute-mev-hack), targets to ge the early attempt to address the problem, and represents a transaction relay that auctions off users' transactions to builders.

## Mechanism description

1. Builders register in the system on permissioned basis (similar to miners accessing Flashbots Relay in PoW Ethereum). 
2. Users send their orders to the relay, which then exposes them to registered builders. At this stage, transactions signatures are hidden. Builders are free to expose some or all of those transactions to searchers integrated with them to incentivise value-extracting transactions.
3. Builders bid the maximum value they’re willing to pay for transactions. Active auctions settle one time each slot, after which builders can query the relay for the transaction signatures and their payment.
4. A builder must include a tx with payment for all transactions they won since their last payment, independently of whether they eventually included a given transaction or not. If builder wins a slot and their block doesn’t contain the payment with correct amount, they lose the access to the relay. (_Disclaimer: we didn't manage to implement this in time_)
5. If a transaction lands on-chain, it is removed from system’s tx pool. Otherwise, it is sent to the public mempool after 10 slots (even if it was sold to a builder) or discarded if it became invalid. Bidders are expected to drop transactions after they become invalid as well.
6. Revenue distribution is out of scope of this project for now, but main ideas include (1) public goods funding (2) monthly reimbursements to users proportionally to revenue generated by their activity (3) fees reduction after account abstraction is introduced to Ethereum.

## Auction format specification

Currently the system sells transactions (1) separately in (2) sealed-bid (3) second-price auctions (4) with reserve price.
1. It makes a lot of sense to allow bundle bids because they allow to capture multi-transaction MEV opportunities, but it makes determining a winner and payment amounts very complicated.
2. Ascending auctions allow for better price discovery and are believed to perform well in cases where items are complements/substitutes. Still, running them in such dynamic environment is hard both for the relay and builders.
3. Sealed-bid second-price auctions are easy for builders as optimal strategy is to just bid expected extracted value. Again, we're making a strong (and wrong) assumption here that items are independet.
4. Reserve price is set roughly to total tx priority fee. This creates an incentive for builders to actually extract value from transactions, instead of simply adding them to fill the blockspace for additional profit.

## Relay API specification

### submitTx

Submit transaction to the relay.The request would fail given hex string doesn't represent the raw transaction, or if transaction is invalid.

`POST /submitTx`

Request payload:
```json
{
    "rawTx": "0x..."
}
```

### register

Register a validator in the system. The request would fail if builder with given key is already registered in the system.

`POST /register`

Request payload:
```json
{
    "pubKey": "0x..."
}
```

### status

Return validator's status. The request would fail if builder with given key is not registered in the system.

`GET /status`

Request payload:
```json
{
    "pubKey": "0x..."
}
```

Successful response payload:
```json
{
    "access": true,
    "pendingPayment": "0"
}
```

### txPool

Return transactions available for sail. The request would fail if builder with given key is not registered in the system, or if their access to the system is restricted.

`GET /txPool`

Request payload:
```json
{
    "pubKey": "0x..."
}
```

Successful response payload:
```json
[
    {
        "data": {
            "from": "0x...",
            "to": "0x...",
            ...
        },
        "reserve": "900000000000"
    },
    ...
]
```

### submitBid

Submit bid on a transaction to the relay. The request would fail if builder with given key is not registered in the system, or if their access to the system is restricted, or if the transaction is not in system's txpool, or if bid value doesn't exceed the reserve price.

`POST /submitBid`

Request payload:
```json
{
    "pubKey": "0x...",
    "txHash": "0x...",
    "value": "1000000000000"
}
```

Successful response payload:
```json
{
    "slot": "4674374"
}
```

### results

Return results of an auction ran in the given slot. The request would fail if builder with given key is not registered in the system, or if their access to the system is restricted.

`GET /results`

Request payload:
```json
{
    "pubKey": "0x...",
    "slot": "4674374"
}
```

Successful response payload:
```json
{
    "total_payment": "10000000000000",
    "transactions": [
        {
            "payment": "900000000000",
            "data": 
        },
        ...
    ]
}
```

## Running and testing

Currently the system can only be ran locally and doesn't have automated tests.

To setup the environment, execute the following commands:

```bash
git clone https://github.com/0xAlchemy/wintermute-hackathon-2022.git order-flow-auctions
cd order-flow-auctions
python3.9 -m venv --upgrade-deps venv
. venv/bin/activate
pip install -r requirements.txt
echo PROVIDER=<YOUR GOERLI PROVIDER URL> >> .env
```

Now, we can run the relay:

```bash
python app.py
```

Finally, we can make some requests from CLI:

```bash
curl -X POST http://127.0.0.1:5000/register \
    -H 'Content-Type: application/json' \
    -d '{"pubKey": "0x0"}'

curl -X GET http://127.0.0.1:5000/getStatus \
    -H 'Content-Type: application/json' \
    -d '{"pubKey": "0x0"}'
```

## Further steps

This project is a prototype of a very large and complicated system. While even these design decisions required considerable mental effort, we're aware of tradeoffs and possible inefficiencies present here. Our main goal is to spur the further discussions on the actual implementation of Order Flow Auctions, so we present the list of potential improvements below.

Short-term:
* Add registration and authentication of builders;
* Add monitoring of builders' payments and access restriction;
* Separate computational logic, storage and web service;
* Properly refactor and test the code.

Long-term:
* Experiment with different combinatorial auction formats that don't assume items independence;
* Design a better payment enforcement mechanism (one idea for permissionless access to the relay is staking ether in a contract; to receive the signatures, bidders would sign permissions to the relay to withdraw the payment amount, and to withdraw their funds they would query the relay for such permission);
* Try to reduce the trust assumptions on both sides;
* Rewrite a system in a language that better suits the purpose :D.
