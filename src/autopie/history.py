from datetime import datetime
import os
import importlib.resources
import pandas as pd
import yfinance as yf

from .util import *

COLUMNS = {
    "stock": "^GSPC",
    "gold": "GC=F",
}

# provides historical data for asset classes prices

MAX_MONTHS = 240

df = None
data_dir = None
data_file = None

def init(filename="history.csv"):
    global data_file
    data_file = filename

    dirs = []

    global data_dir
    data_dir = os.environ.get("XDG_DATA_HOME", "~/.local/share")
    data_dir = os.path.expanduser(f"{data_dir}/autopie")
    dirs.append(data_dir)

    dirs.append(str(importlib.resources.files() / "data"))

    debug(f"history: searching data in {dirs}")

    found = False
    for d in dirs:
        history_file = os.path.join(d, filename)
        if os.path.exists(history_file):
            found = True
            trace(f"history: found {history_file}")
            break
    if not found:
        error(f"history: csv not found, filename {filename} dirs {dirs}")

    global df
    df = pd.read_csv(history_file)
    trace(f"history: dataframe {df}")
    trace(f"history: read dataframe")

    # Add missing rows
    last_row = df.iloc[-1]
    last_year = int(last_row["year"])
    last_month = int(last_row["month"])
    now = datetime.now()
    this_year = now.year
    this_month = now.month
    debug(f"last {last_year}-{last_month}, this {this_year}-{this_month}")
    assert(last_year <= this_year)
    if last_year == this_year:
        assert(last_month <= this_month)

    to_add = pd.DataFrame([], columns=df.columns)
    m = last_month
    for y in range(last_year, this_year+1):
        start_m = 1
        if y == last_year:
            start_m = last_month+1
        end_m = 12
        if y == this_year:
            end_m = this_month-1
        for m in range(start_m, end_m+1):
            trace(f"Empty row for year {y} month {m}")
            row = pd.DataFrame([[y, m] + [None]*(len(df.columns)-2)], columns=df.columns)
            debug(f"Row: {row}")
            to_add = pd.concat([to_add, row], ignore_index=True)
    if not to_add.empty:
        df = pd.concat([df, to_add], ignore_index=True)

    # fill missing values
    debug(f"history: setting missing values")
    for column in COLUMNS.values():
        ticker = column
        trace(f"history: column {column}")
        for ri, data in df.iloc[-MAX_MONTHS:].iterrows():
            if pd.isna(data[column]):
                trace(f"history: Null value for column {column} in row {ri}")
                y = int(data["year"]) # WTF it tends to cast it to numpy.float64
                m = int(data["month"])
                if m == 12:
                    yn = y + 1
                    mn = 1
                else:
                    yn = y
                    mn = m + 1
                value = yf.Ticker(ticker).history(
                            start=f"{y}-{m}-1",
                            end=f"{yn}-{mn}-1",
                            interval="1d")["Close"].mean()
                value = round(value, 2)
                trace(f"history: going to set {column} {y}-{m} to {value} {type(value)}")
                df.at[ri, column] = value
                debug(f"history: set {column} {y}-{m} to {value} {type(value)}")


def stats(ac, freq="month", num=240, until="last"):
    trace(f"history: getting stats for {ac}")
    column = COLUMNS[ac]
    if column not in df.columns:
        error(f"history: column {column} for asset class {ac} not present in columns {df.columns}")
    if until == "last":
        now = datetime.now()
        year = now.year
        month = now.month
        if month == 1:
            until = (year-1, 12)
        else:
            until = (year, month-1)
    assert(len(until) == 2)
    trace(f"history: until: {until}")

    end = df.loc[df["year"]==until[0]].loc[df["month"]==until[1]].index[0] + 1
    start = end - num

    debug(f"Start: {start}")
    debug(f"End: {end}")
    debug(f"Rows: {df.iloc[start:end]}")
    ticker = COLUMNS[ac]
    current = yf.Ticker(ticker).get_fast_info()["lastPrice"]
    result = {
            "current": round(current, 2),
            "mean": round(float(df.iloc[start:end][column].mean()), 2),
            "min": round(float(df.iloc[start:end][column].min()), 2),
            "max": round(float(df.iloc[start:end][column].max()), 2),
    }
    debug(f"history: stats result for {ac}: {result}")

    return result

def clean():
    trace("history: cleanup start")
    # save dataframe to data directory
    if data_dir is not None and data_file is not None:
        trace(f"history: saving to {data_dir}/{data_file}")
        df.to_csv(f"{data_dir}/{data_file}", index=False)
        debug(f"history: saved to {data_dir}/{data_file}")
    trace("history: cleanup finished")
