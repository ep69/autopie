#!/usr/bin/env python3

from decimal import Decimal

from ..core import Provider, Price, Product, Asset

# TODO make more generic - directly setting assets in config
class Physical(Provider):
    """Physical, offline or not yet integrated assets"""

    def init(self, **data):
        self._assets = [
            Asset(
                product=Product(
                    name="gold_physical",
                    aclass="gold",
                    price=Price(data["goldoz_czk"], "czk"),
                    provider=self._name
                    ),
                amount=data["gold_physical"],
                ),
        ]

    def clean(self):
        pass
