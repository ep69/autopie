#!/usr/bin/env python3

from pprint import pprint, pformat
from decimal import Decimal
from math import floor
import os
import sys
import dotenv
import tomllib
from copy import deepcopy
import click
from click_default_group import DefaultGroup
import importlib.metadata

from .core import AbstractPortfolio, RealPortfolio, Price, Provider, Strategy
from .util import *

# TODO discover and import all providers dynamically
from .providers.offline import Offline
from .providers.xtb_treasury import XTB
from .providers.kraken import Kraken

from .currency import get_rate
from . import storage
from . import history

# Design:
# 1. get holdings
# 2. get prices
# 3. compute actual portfolio
# 4. compare with desired portfolio
# 5. buy

def substitute_secrets(secrets, data):
    if isinstance(data, dict):
        print(f"dict {data}")
        for k,v in data.items():
            if isinstance(v, str) and v.startswith("$"):
                print(f"string ({k}) {v}")
                data[k] = secrets[v[1:]]
            else:
                debug(f"nonstring ({k}) {v} {type(v)}")
                substitute_secrets(secrets, v)
    elif isinstance(data, list):
        for i in data:
            substitute_secrets(secrets, i)
    else:
        debug(f"substitute_secrets: type of {data} is {type(data)}")
        return

@click.group(cls=DefaultGroup, default='invest', default_if_no_args=True)
def main():
    pass

@main.command()
def version():
    print(importlib.metadata.version("autopie"))

@main.command()
@click.option(
        "-d", "--debug", "debug_level",
        type=click.IntRange(min=0, max=2),
        default=0,
        show_default=True,
        help="Debug level",
    )
@click.option(
        "--config-dir",
        type=click.Path(file_okay=False),
        envvar="AUTOPIE_CONFDIR",
        default=os.environ.get("XDG_CONFIG_HOME", "~/.config")+"/autopie",
        show_default=True,
        help="Configuration directory",
    )
def invest(debug_level, config_dir):
    set_verbose(debug_level)
    info(f"Debug: {debug_level}")

    debug(f"config dir {config_dir}")
    config_dir = os.path.expanduser(config_dir)
    debug(f"config dir expanded {config_dir}")
    config_file = os.path.join(config_dir, "config.toml")
    debug(f"Reading config file {config_file}")
    with open(config_file, "rb") as fp:
        config = tomllib.load(fp)
    print(f"Config: {config}")
    assert(config["version"] == 1)

    if "secrets_file" in config:
        secrets_file = os.path.join(config_dir, config["secrets_file"])
        debug(f"Secrets file: {secrets_file}")
        secrets = dotenv.dotenv_values(secrets_file)
        debug(f"Secrets:")
        for k,v in secrets.items():
            debug(f"  {k}: {v}")
        substitute_secrets(secrets, config)
        #debug(f"Config with secrets: {pformat(config)}")

    history.init()

    data_dir = os.environ.get("XDG_DATA_HOME", "~/.local/share")
    data_dir = os.path.expanduser(f"{data_dir}/autopie")
    storage_file = os.path.join(data_dir, config.get("storage_file", "data.store"))
    debug(f"Storage file: {storage_file}")
    storage.init(storage_file)

    debug(f"Available providers: {[P.__name__.lower() for P in Provider.providers]}")
    debug(f"Configured providers: {[p.lower() for p in config['providers']]}")

    providers = []
    for p in config["providers"]:
        provider_name = p.lower()
        found = False
        debug(f"Searching for provider {provider_name}")
        for P in Provider.providers:
            if provider_name == P.__name__.lower():
                found = True
                provider = P() # TODO: init directly in __init__? maybe not so modules are usable
                provider.init(**config["providers"][p]["data"])
                providers.append(provider)
                break
        if not found:
            error(f"Configured provider {p} not available")

    # get strategies
    config_strategies = config.get("strategies", None)
    total_weight = Decimal(0)
    if config_strategies is None:
        s = config.get("strategy", None)
        if s is None:
            error(f"No strategies configured.")
        config_strategies = [s]
    strategies = []
    for s in config_strategies:
        strategy_name = s.get("name", None)
        if strategy_name is None:
            error(f"No strategy name configured.")
        if "weight" not in s:
            error(f"No weight for strategy {strategy_name}")
        total_weight += Decimal(s["weight"])
        strategy = None
        for S in Strategy.strategies:
            if S.__name__.lower() == strategy_name.lower():
                debug2(f"Strategy {strategy_name} found")
                strategy = S(**s)
        if strategy is None:
            error(f"Cannot find strategy")
        strategies.append(strategy)
    if len(strategies) == 0:
        error(f"No strategies loaded")
    else:
        debug(f"Strategies loaded: {[s.name for s in strategies]}")

    # get ideal portfolio
    ip = config.get("ideal", {})
    if len(ip) == 0:
        error(f"No ideal portfolio set")
    ideal = AbstractPortfolio(values=ip)

    assets = []
    for provider in providers:
        assets.extend(provider.assets)
    for asset in assets:
        print(asset)

    # TODO manage defaults better?
    currency=config.get("currency", "usd")
    original_real = RealPortfolio.from_assets(assets=assets, currency=currency)
    original_abstract = AbstractPortfolio(values=original_real.ratios)

    spend_amount = config["spend"]["amount"] # TODO better error handling
    spend_currency = config["spend"]["currency"]
    spend_money = Price(spend_amount, spend_currency)
    spend_value = spend_money.num * get_rate(spend_money.unit, currency)

    portfolio_to_buy = RealPortfolio(currency=currency)
    for strategy in strategies:
        debug2(f"iterating strategies: {strategy.name}")
        to_buy_abstract = strategy.action(ideal, original_abstract)
        debug(f"To buy abstract: [{to_buy_abstract}]")
        to_buy_real = RealPortfolio(currency=currency, values={ac: Decimal(ratio)*spend_value for ac, ratio in to_buy_abstract.ratios.items()})
        debug(f"To buy real: {to_buy_real}")
        adjusted_weight = strategy.weight / total_weight
        to_buy_real *= adjusted_weight
        debug(f"To buy real (adjusted by {adjusted_weight}): {to_buy_real}")
        portfolio_to_buy += to_buy_real
        debug(f"Portfolio to buy (step): {portfolio_to_buy}")
    debug(f"Portfolio to buy (computed strategies): {portfolio_to_buy}")
    storage_remains = storage.load("remains")
    debug(f"Storage remains: {storage_remains}")
    if storage_remains is not None:
        debug(f"Storage: loaded {storage_remains}")
        portfolio_to_buy += storage_remains
    debug(f"Portfolio to buy (loaded storage): {portfolio_to_buy}")
    portfolio_to_buy.remove("cash")
    debug(f"Portfolio to buy (cash removal): {portfolio_to_buy}")
    info(f"Portfolio to buy: {portfolio_to_buy}")

    remains = deepcopy(portfolio_to_buy)
    total_bought = RealPortfolio(currency=currency)
    for provider in providers:
        debug2(f"Provider {provider.name} trying to buy {remains}")
        bought = provider.buy_real_portfolio(remains)
        debug2(f"Provider {provider.name} bought {bought}")
        remains -= bought
        total_bought += bought
        debug2(f"After provider {provider.name} remains {remains}")
    debug(f"Storage: saving {remains}")
    storage.save("remains", remains)
    storage.save("original_real", original_real)
    storage.save("original_abstract", original_abstract)
    storage.save("ideal", ideal)

    # TODO warn? error? make more robust?
    debug(f"Wanted to buy: {portfolio_to_buy}")
    debug(f"Bought: {total_bought}")
    debug(f"Remained: {remains}")

    for provider in providers:
        debug2(f"Provider {provider.name} cleanup")
        provider.clean()

    history.clean()

    return 0

# TODO:
# * logging
