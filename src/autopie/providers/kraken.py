#!/usr/bin/env python3

import time
import krakenex

from autopie.core import Provider, Product, Asset, Price
from autopie.util import *

class Kraken(Provider):

    def init(self, **data):
        debug(f"Provider Kraken({self.name}) init: {data}")
        self._dryrun = data.get("dryrun", False)

        token_key = data.get("token_key", None)
        token_secret = data.get("token_secret", None)
        self._currency = data.get("currency", None)

        if any(elem is None for elem in (token_key, token_secret, self._currency)):
            raise ValueError("Kraken: token_key, token_secret, and currency needed")

        self._k = krakenex.API(key=token_key, secret=token_secret)

        # TODO possibility to use keyfile
        #self._k.load_key(keyfile)

        self._refresh_assets()

    def clean(self):
        self._k.close()

    ASSET_CLASSES = {
        "XXBT": "btc",
        "ZEUR": "cash",
        "ZUSD": "cash",
    }

    @classmethod
    def _aclass(cls, abbrev):
        return cls.ASSET_CLASSES.get(abbrev, "unknown")


    def _refresh_assets(self):
        trace(f"Querying: Balance")
        data = self._k.query_private("Balance")
        trace(f"Returned: {data}")
        result = data.get("result", None)
        if result is None:
            error(f"Kraken: cannot get balance")

        products = []
        assets = []
        for k,v in result.items():
            debug(f"Kraken: processing balance {k}: {v}")
            amount = float(v)
            if amount == 0.0:
                trace(f"Kraken: zero amount for {k}")
                continue
            else:
                trace(f"Kraken: non-zero amount for {k}: {amount}")
            if k == "KFEE": # ignore fee credit
                continue

            ac = self._aclass(k)
            if ac == "unknown":
                warn(f"Kraken: unknown asset {k}, skipping")
                continue

            price = None
            other = {}
            if ac == "cash":
                name = k
                curr = k[-3:]
                price = Price(num=1, unit=curr)
            elif ac == "btc":
                pair = f"btc/{self._currency}"
                trace(f"Querying: Ticker {pair}")
                data = self._k.query_public("Ticker", {"pair": f"{pair}"})
                pairdata = data.get("result", {}).get(pair.upper(), None)
                if pairdata is None:
                    error(f"cannot get Ticker data for {pair}")

                trace(f"Kraken Querying: AssetPairs {pair}")
                data = self._k.query_public("AssetPairs", {"pair": pair})
                result = data.get("result", {})
                if len(result) != 1:
                    error(f"Kraken: unexpected number of AssetPairs results for {pair}: {data}")
                name = list(result.keys())[0]
                ordermin = result[name]["ordermin"]
                debug(f"Kraken ordermin for {name}: {ordermin}")
                other["ordermin"] = float(ordermin)

                price = Price(
                        num=float(pairdata["a"][0]),
                        unit=self._currency,
                        )
            else:
                error(f"Cannot get price of {k}")
            assert(price is not None)

            product = Product(
                name=name,
                aclass=ac,
                price=price,
                provider=self._name,
                other=other,
            )
            if product.aclass != "cash":
                products.append(product)

            assets.append(
                Asset(
                    product=product,
                    amount=amount,
                    )
            )

        self._products = products
        self._assets = assets

    @property
    def buyable(self): # -> [ product ]
        return self._products


    def buy(self, product, amount):
        trace(f"Kraken buying {amount} of {product}")

        ordermin = product.other["ordermin"]
        debug(f"Kraken minimum for {product.name}: {ordermin}")
        if amount <= ordermin:
            debug(f"Cannot buy {amount:.8f} of {product.name}, minimum is {ordermin}")
            return 0.0

        buy_data = {
            "pair": product.name,
            "type": "buy",
            "ordertype": "market",
            "leverage": "none",
            "volume": str(amount),
        }
        if self._dryrun:
            trace("Kraken: Dryrun, just validate the transaction")
            buy_data["validate"] = True
        trace(f"Kraken request: AddOrder request data: {buy_data}")

        t = 0
        MAX_TRIES = 5
        DELAY_INC = 60
        while t < MAX_TRIES:
            trace(f"Buy loop: iteration {t}")
            t += 1

            reply = self._k.query_private("AddOrder", buy_data)
            trace(f"Kraken AddOrder returned: {reply}")
            err = reply["error"]

            recoverable_errors = [
                    "EService:Busy",
                    "EService:Unavailable",
                    "EService:Market in post_only mode",
                    "EService:Market in cancel_only mode",
                    "EGeneral:Internal error",
                    "EService:Internal error",
                    "EDatabase:Internal error",
                    "EGeneral:Timeout",
                    ]
            if len(err) >= 1 and err[0] in recoverable_errors:
                delay = t * DELAY_INC
                debug(f"Kraken buy loop: recoverable error {err}, waiting {delay} seconds")
                time.sleep(delay)
            elif err:
                for m in err:
                    warn(f"Buy error: {m}")
                return 0.0
            else: # success
                trace(f"Kraken buy loop: success")
                return amount

        # "timeout", no iteration succeeded
        return 0.0
