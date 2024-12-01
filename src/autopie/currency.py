import requests
from decimal import Decimal
from .util import *

cache = {}

def get_rate(base, quote):
    trace(f"get_rate: converting {base} to {quote}")
    global cache
    base = base.strip().lower()
    quote = quote.strip().lower()

    if base not in cache:
        trace(f"get_rate: base {base} not in cache, retrieving")
        url = f"https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{base}.min.json"

        resp = requests.get(url=url)
        if resp.status_code not in [200]:
            return None

        data = resp.json().get(base, None)
        if data is None:
            error(f"get_rate: no currency data for base '{base}'")
        cache[base] = data

    value = Decimal(cache.get(base, {}).get(quote, None))
    trace(f"get_rate: 1{base} = {value:.2f}{quote}")

    return value
