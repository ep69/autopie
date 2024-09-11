import json
import time
from websocket import create_connection, WebSocketConnectionClosedException
import pprint
from math import ceil

from ..currency import get_rate
from ..core import Provider, Price, Product, Asset
from ..util import *

class XTB(Provider):
    @staticmethod
    def _ws_mkcmd(command, **args):
        data = {
            "command": command,
        }
        if args:
            data['arguments'] = {}
            for (key, value) in args.items():
                data['arguments'][key] = value
        debug2(f"mkcmd data: {data}")
        return data

    def _ws_send(self, command, **args):
        debug2(f"XTB _ws_send {command}: {args}")
        dict_data = self._ws_mkcmd(command, **args)
        time.sleep(0.2)
        try:
            self._ws.send(json.dumps(dict_data))
            r = self._ws.recv()
        except WebSocketConnectionClosedException:
            return (False, "web socket closed")
        res = json.loads(r)
        debug2(f"ws_send res: {res}")
        res_data = None
        if 'returnData' in res.keys():
            res_data = res['returnData']
        return (res['status'], res_data)

    def init(self, **data):
        debug2(f"Provider XTB({self.name}) init: {data}")
        ws = data.get("url", None)
        login = data.get("login", None)
        pw = data.get("password", None)

        if any(elem is None for elem in (ws, login, pw)):
            raise ValueError("url, login and password needed")

        self._ws = create_connection(ws)
        status, data = self._ws_send("login", userId=login, password=pw)
        debug2(f"login: {status} {data}")
        # TODO die if login failed
        self._get_currency()
        self._refresh_assets()

    def clean(self):
        self._ws_send("logout")

    _ASSET_CLASSES = {
        "VWRA.UK": "stock",
        "IGLN.UK": "gold",
        "IGLN.UK_9": "gold",
        "IB01.UK": "cash",
    }

    @classmethod
    def _symbol_aclass(cls, symbol):
        return cls._ASSET_CLASSES.get(symbol, "unknown")

    def _get_currency(self):
        status, data = self._ws_send("getCurrentUserData")
        debug2(f"XTB buy getCurrentUserData sent {status} {data}")
        if status:
            ac = data.get("currency", None)

        if ac is None:
            error(f"XTB: cannot get account currency")

        self._account_currency = ac.strip().lower()

    def _refresh_assets(self):
        debug2(f"Provider XTB({self.name}) _refresh_assets")
        products = []
        assets = []
        status, data = self._ws_send("getTrades", openedOnly=True)
        debug2(f"XTB getTrades(openedOnly=True): {status}: {json.dumps(data, indent=4)}")
        if not status:
            error("XTB getTrades")
        pf_amounts = {}
        for r in data:
            symbol = r["symbol"]
            pf_amounts[symbol] = pf_amounts.get(symbol, 0.0) + r["volume"]
        debug2(f"XTB sum: {pprint.pformat(pf_amounts)}")
        values = {}
        # move somewhere else?
        for symbol in self._ASSET_CLASSES:
            if symbol not in pf_amounts:
                pf_amounts[symbol] = 0.0
        for symbol, amount in pf_amounts.items():
            status, data = self._ws_send("getSymbol", symbol=symbol)
            if not status:
                # some symbols are different in real and demo version,
                # e.g., IGLN.UK / IGLN.UK_9; continue if not found
                debug2(f"XTB getSymbol {symbol} not found (data: {data})")
                continue
            debug2(f"XTB getSymbol({symbol}): {pprint.pformat(data)}")
            avg_price = (data["bid"]+data["ask"] ) / 2
            currency = data["currency"]
            product=Product(
                name=symbol,
                aclass=self._symbol_aclass(symbol),
                price=Price(avg_price, currency),
                provider=self._name
                )
            products.append(product)
            assets.append(
                Asset(
                    product=product,
                    amount=amount,
                )
            )
        self._products = products
        debug(f"XTB assets: {pprint.pformat(assets)}")
        self._assets = assets

    @property
    def buyable(self):
        return self._products

    def _get_free_cash(self):
        status, data = self._ws_send("getMarginLevel")
        debug2(f"XTB buy getMarginLevel sent {status} {data}")
        if status:
            return data.get("balance", None)

        return None

    def _sell(self, product, amount):
        debug2(f"XTB selling {amount} of {product}")
        tti = {
            "cmd": 1, # SELL
            "price": float(product.price.num),
            "symbol": product.name,
            "type": 0, # OPEN
            "volume": float(amount)
        }
        status, data = self._ws_send("tradeTransaction", tradeTransInfo=tti)
        debug2(f"XTB _sell tradeTransaction sent {status} {data}")
        if not status:
            warn(f"XTB _sell error: {data}")
            return False
        order = data.get("order", None)
        if not order:
            warn(f"XTB _sell error: no order data")
            return False

        status, data = self._ws_send("tradeTransactionStatus", order=order)
        if not status:
            warn(f"XTB status error: {data}")
            return False
        debug2(f"XTB _sell tradeTransactionStatus sent {status} {data}")
        order_status = data.get("requestStatus", None)
        if order_status is None:
            warn(f"XTB _sell error: no requestStatus")
            return False

        if order_status in (1, 3):
            # order is PENDING or ACCEPTED
            debug(f"XTB sold {amount} of {product}")
            return True
        return False

    def buy(self, product, amount):
        debug2(f"XTB buying {amount} of {product}")

        free_cash = self._get_free_cash()
        need_cash = float(amount * product.price.num * get_rate(product.price.unit, self._account_currency))
        if free_cash < need_cash:
            debug(f"XTB buy needs more cash: free cash {free_cash:.2f}, need {need_cash:.2f}")
            # need to sell IB02.UK
            CASH_PRODUCT_NAME="IB01.UK"
            cash_product = None
            for p in self._products:
                if p.name == CASH_PRODUCT_NAME:
                    cash_product = p
                    break
            if cash_product is None:
                error(f"XTB buy error: cash product not found")
            sell_amount = ceil(
                    (need_cash-free_cash)*1.1
                    / float(cash_product.price.num*get_rate(cash_product.price.unit, self._account_currency))
                )
            res = self._sell(cash_product, sell_amount)
            if not res:
                warn(f"XTB error selling {sell_amount} of cash product {cash_product}")
                return False
            debug2(f"XTB buy: successfully sold {sell_amount} of {cash_product.name}")
        tti = {
            "cmd": 0, # BUY
            #"customComment": f"buying {amount} of {product.name} ",
            #"expiration": None,
            #"offset": 0,
            #"order": 0,
            "price": float(product.price.num),
            #"sl": 0.0,
            "symbol": product.name,
            #"tp": 0.0,
            "type": 0, # OPEN
            "volume": float(amount)
        }
        status, data = self._ws_send("tradeTransaction", tradeTransInfo=tti)
        debug2(f"XTB buy tradeTransaction sent {status} {data}")
        if not status:
            warn(f"XTB buy error: {data}")
            return False
        order = data.get("order", None)
        if not order:
            warn(f"XTB buy error: no order data")
            return False

        status, data = self._ws_send("tradeTransactionStatus", order=order)
        if not status:
            warn(f"XTB status error: {data}")
            return False
        debug2(f"XTB buy tradeTransactionStatus sent {status} {data}")
        order_status = data.get("requestStatus", None)
        if order_status is None:
            warn(f"XTB buy error: no requestStatus")
            return False

        if order_status in (1, 3):
            # order is PENDING or ACCEPTED
            debug(f"XTB bought {amount} of {product}")
            return True
        return False

