
from typing import Protocol
from decimal import Decimal
from math import floor
from abc import ABC, abstractmethod
import numbers
import string
from copy import deepcopy

from .util import *
from .currency import get_rate

# class Price: ? # number, currency
# class Product: ? # or just dict # should include price, class
# class Asset: ? # product, num

class Price:
    def __init__(self, *args, num=None, unit=None):
        if len(args) >= 1 and len(args) <= 2:
            debug2(f"Price args: {args}")
            if num is not None or unit is not None:
                error(f"Price: extra num ({num}) and or unit ({unit})")
            if len(args) == 2:
                self.num = args[0]
                self.unit = args[1]
            else: # len(args) == 1
                s = args[0].strip()
                self.num = s.rstrip(string.ascii_letters+string.whitespace)
                self.unit = s.lstrip("."+string.digits+string.whitespace)
        elif len(args) == 0:
            if num is None or unit is None:
                error(f"Price: missing num ({num}) or unit ({unit})")
            self.num = num
            self.unit = unit
        else: # len(args) >= 3
            error(f"Price: too many args ({args})")

        self.num = Decimal(self.num) # e.g., 20.5
        self.unit = self.unit.lower() # e.g., "usd"

    def __str__(self):
        return f"{self.num:.2f}{self.unit}"

    def __repr__(self):
        return str(self)

class Product:
    def __init__(self, name, aclass, price, provider):
        self.name = name
        self.aclass = aclass
        self.price = price
        self.provider = provider
    def __str__(self):
        #return f"{self.name} ({self.aclass}, {str(self.price)})"
        return f"[{self.aclass}] ({self.name} @{str(self.price)} /{self.provider})"
    def __repr__(self):
        return str(self)

class Asset:
    def __init__(self, product, amount):
        self.product = product
        self.amount = Decimal(amount)
        assert self.amount >= 0
    def __str__(self):
        return f"{str(self.product)} x{self.amount:.2f}"
    def __repr__(self):
        return str(self)

# TODO think more about which methods to make abstact
# maybe add some helper subclasses like "SimpleProvider" (containing what is here) and use Provider really as interface
# maybe specific class for storage-only providers (physical)
class Provider(ABC):
    providers = []

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.providers.append(cls)

    @classmethod
    def register(cls, new_provider):
        cls.providers.append(new_provider)

    def __init__(self, name=None):
        if name is None:
            self._name = self.__class__.__name__.lower()
        else:
            self._name = name
    @property
    def name(self): # -> "string"
        return self._name
    @abstractmethod
    def init(self, **data):
        """Initialize provider"""
    @abstractmethod
    def clean(self):
        """Deinitialize provider"""
    @property
    def assets(self): # -> [ asset ]
        return self._assets
    @property
    def buyable(self): # -> [ product ]
        return []
    def buy(self, product, amount):
        raise NotImplementedError
    def buy_aclass(self, aclass, price):
        debug(f"Provider {self.name} buy_aclass {aclass} for {price}")
        debug(f"Provider {self.name} buyable products: {self.buyable}")
        product = None
        for p in self.buyable:
            if p.aclass == aclass:
                product = p
                break
        if product is None:
            return None
        debug(f"Provided {self.name} buy_aclass found product {product}")
        amount = floor(price.num / get_rate(product.price.unit, price.unit) / product.price.num)
        debug(f"buy_aclass: computing amount: {price.num:.2f} / {get_rate(product.price.unit, price.unit):.2f} / {product.price.num:.2f} = {amount}")
        assert(amount >= 0)
        if amount < 1:
            warn(f"buy_aclass: not buying zero amount")
            return None
        res = self.buy(product, amount)
        if res:
            return RealPortfolio(values={aclass: amount*product.price.num}, currency=product.price.unit)
        else:
            return None

    def buy_real_portfolio(self, portfolio):
        debug(f"buy_real_portfolio: provider {self.name}, portfolio to buy {portfolio}")
        currency = portfolio.currency
        total_bought = RealPortfolio(currency=currency)
        debug2(f"buy_real_portfolio: provider {self.name}, total_bought init {total_bought}")
        for ac, amount in portfolio.values.items():
            debug2(f"buy_real_portfolio: provider {self.name}, trying to buy {ac} {amount:.2f}")
            bought = self.buy_aclass(ac, Price(amount, currency))
            debug(f"buy_real_portfolio: provider {self.name}, tried to buy {ac} {amount:.2f}, bought {bought}")
            if bought is not None:
                debug(f"Provider {self.name} bought: {bought}")
                total_bought += bought
            debug2(f"buy_real_portfolio: provider {self.name}, total_bought step {total_bought}")
        debug(f"buy_real_portfolio: provider {self.name}, total_bought {total_bought}")
        return total_bought # what was bought


class AbstractPortfolio:
    def __init__(self, *, values={}):
        self._values = values
        self._total = sum(values.values())

    @property
    def ratios(self):
        values = self._values
        total = self._total
        ratios = {}
        for k, val in values.items():
            ratios[k] = val / total
        return ratios

    def __str__(self):
        return " | ".join([f"{ac}: {ratio:.2f}"
                for ac, ratio in sorted(self.ratios.items(), key=lambda x: x[0])
           ])

    def __repr__(self):
        return str(self)


class RealPortfolio:
    @classmethod
    def from_assets(cls, *, assets, currency):
        values = {}
        for a in assets:
            aclass = a.product.aclass
            values[aclass] = values.get(aclass, Decimal(0)) + Decimal(
                    a.amount
                    * a.product.price.num
                    * get_rate(a.product.price.unit, currency)
                )
            assert values[aclass] >= 0
        return RealPortfolio(currency=currency, values=values)

    @classmethod
    def from_dict(cls, *, d):
        debug(f"from_dict: {d}")
        assert d["class"] == cls.__name__
        debug(f"from_dict: currency {d['currency']}")
        debug(f"from_dict: values {d['values']}")
        return cls(
                currency=d["currency"],
                values={
                    ac: Decimal(str_dec) for ac, str_dec in d["values"].items()
                },
            )

    def to_dict(self):
        return {
                "class": self.__class__.__name__,
                "currency": self._currency,
                "values": {
                        ac: str(dec) for ac, dec in self._values.items()
                    }
            }

    def __init__(self, *, values=None , currency="USD"):
        debug2(f"RealPortfolio __init__: values {values}, currency {currency}")
        if type(currency) is not str or len(currency) != 3:
            error(f"RealPortfolio: bad currency {currency}")
        self._currency = currency.lower()

        if values is None:
            self._values = {}
        else:
            self._values = values
            for v in values.values():
                assert v >= 0

    def _add_asset(self, a):
        return NotImplementedError()
        if type(a) is not Asset:
            error(f"RealPortfolio: {a} is not an Asset")
        self._assets.append(a)

        aclass = a.product.aclass
        self._values[aclass] = self._values.get(aclass, Decimal(0)) + Decimal(
                a.amount
                * a.product.price.num
                * get_rate(a.product.price.unit, self._currency)
            )

    def add(self, a):
        return NotImplementedError()
        if type(a) is list:
            for i in a:
                self._add_asset(i)
        else:
            self._add_asset(a)

    def remove(self, ac):
        if ac in self._values:
            debug2(f"RealPortfolio: removing {ac} from {self}")
            del self._values[ac]
            debug2(f"RealPortfolio: removed {ac} from {self}")


    def __iadd__(self, other):
        debug(f"RealPortfolio +=: other {other}")
        rate = get_rate(other.currency, self.currency)
        for ac, ov in other.values.items():
            assert ov >= 0
            self._values[ac] = self._values.get(ac, Decimal(0)) + ov*rate
        return self

    def __isub__(self, other):
        # TODO what to do with self.assets?
        for oc, ov in other.values.items():
            if oc not in self.values:
                error(f"RealPortfolio: -= not possible for {oc}")
            price = self.values[oc]
            price -= ov * get_rate(other.currency, self.currency)
            assert price >= 0
            self._values[oc] = price
        return self

    def __mul__(self, other):
        m = Decimal(other)
        assert m >= 0
        for k,v in self._values.items():
            self._values[k] = m * v
        return self

    __rmul__ = __mul__

    @property
    def currency(self):
        return self._currency

    @property
    def assets(self):
        return NotImplementedError()
        #return self._assets

    # returns { aclass -> num }
    @property
    def values(self):
        return self._values

    @property
    def total(self):
        return sum(self._values.values())

    @property
    def ratios(self):
        values = self.values
        total = self.total
        assert total >= 0
        ratios = {}
        for aclass, val in values.items():
            assert val >= 0
            ratios[aclass] = val / total
        return ratios

    def __str__(self):
        return ( f"RealPortfolio({self.currency} {sum(self._values.values()):.2f}: "
            + (
                " ".join(f"[{ac}: {v:.2f}]" for ac, v in self._values.items())
                if self._values
                else "empty"
              )
            #+ f", total {sum(self._values.values()):.2f}"
            + ")"
            )

    def __repr__(self):
        return str(self)


# in general: ?what to put in __init__ and what to specify in args?
# * how much to spend
# * current portfolio (args)
# * ideal portfolio (args)
# ? time
# -> buy pie
class Strategy(ABC):
    strategies = []

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.strategies.append(cls)

    @classmethod
    def register(cls, new_strategy):
        cls.strategies.append(new_strategy)

    def __init__(self, *, name=None, weight=None, **kwargs):
        if name is None:
            error(f"No name strategy in {self.__class__.__name__}")
        self.name = name

        if weight is None:
            error(f"No weight for strategy {name}")
        self.weight = Decimal(weight)

        for k, v in kwargs.items():
            warn(f"Strategy {name}: unknown argument {k}: {v}")

    @abstractmethod
    def action(self, ideal, current):
        """
        Return how to allocate asset classes toward `ideal` portfolio.
        All values are relative.
        """

class DCAStrategy(Strategy):
    def action(self, ideal, current):
        return deepcopy(ideal)

class MinRatioAssetStrategy(Strategy):
    def action(self, ideal, current):
        debug(f"MinRatioAssetStrategy: ideal {ideal}")
        debug(f"MinRatioAssetStrategy: current {current}")
        aclass = None
        min_ratio = Decimal(2) # 200%
        # get the most underweight asset class
        for ac, ideal_ratio in ideal.ratios.items():
            current_ratio = current.ratios.get(ac, Decimal(0))
            ratio = current_ratio / Decimal(ideal_ratio) # TODO why is Decimal(ideal_value) needed?
            if ratio < min_ratio:
                aclass = ac
                min_ratio = ratio
        if aclass is None:
            return None
        # spend all on this asset
        return AbstractPortfolio(values={aclass: Decimal(1)})

