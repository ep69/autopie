#!/usr/bin/env python3
# Read-only provider for offline asset

from decimal import Decimal

from ..core import Provider, Price, Product, Asset

# TODO make more generic - directly setting assets in config
class Offline(Provider):
    """Physical, offline or not yet integrated assets"""

    def init(self, **data):
        self._assets = []
        for asset in data.get("assets", []):
            a = Asset(
                product=Product(
                    name=asset["name"],
                    aclass=asset["aclass"],
                    price=Price(float(asset["price"]), asset["currency"]),
                    provider=self._name
                    ),
                amount=float(asset["amount"]),
            )
            self._assets.append(a)
        

    def clean(self):
        pass
