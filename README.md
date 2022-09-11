# Usage examples

## Get mempool

``` bash
curl -X GET http://127.0.0.1:5000/txPool \
    -H 'Content-Type: application/json' \
    -d '{"pubKey": "0x0"}'
```

## Submit bid

``` bash
curl -X POST http://127.0.0.1:5000/submitBid \
    -H 'Content-Type: application/json' \
    -d '{"pubKey": "0x0", "txHash": "0x0", "value": "5"}'
```

## Get results

``` bash
curl -X GET http://127.0.0.1:5000/results \
    -H 'Content-Type: application/json' \
    -d '{"pubKey": "0x0"}'
```
