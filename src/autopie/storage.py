#!/usr/bin/env python3

import os
import sys
import json
import pickle
import codecs
from .util import *

VERSION = 1
STORAGE = None

def init(storage_path):
    global STORAGE

    STORAGE = storage_path
    debug(f"Storage file: {STORAGE}")

    # if storage file does not exist, create it
    if not os.path.exists(STORAGE):
        debug(f"Storage: STORAGE {STORAGE} does not exist, creating")
        os.makedirs(os.path.dirname(STORAGE), exist_ok=True)
        os.mknod(STORAGE, mode=0o600)
        _write_file(STORAGE, {"version": VERSION, "store": {}})

def _read_file(file):
    with open(file, mode="r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["version"] == VERSION
    return data

def _write_file(file, data):
    debug(f"storage: writing to {file}: {data}")
    with open(file, mode="w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def _wrap(data):
    debug2(f"storage: _wrap: {data}")
    # try json.dumps
    try:
        _ = json.dumps(data)
        # data is json-dumpable
        return {
                "type": "json",
                "data": data,
            }
    except TypeError:
        # data not json-dumpable
        pass

    # pickle and encode in base64
    return {
            "type": "b64pickle",
            "data": codecs.encode(pickle.dumps(data), "base64").decode(),
            ".str": str(data),
        }

def _unwrap(data):
    debug2(f"storage: _unwrap: {data}")
    if not all(key in data for key in ("type", "data")):
        return None
    match data["type"]:
        case "json":
            return data["data"]
        case "b64pickle":
            return pickle.loads(codecs.decode(data["data"].encode(), "base64"))
        case _:
            return None

def save(key, value):
    assert STORAGE is not None
    debug(f"storage: save: {key} -> {value}")
    data = _read_file(STORAGE)
    data["store"][key] = _wrap(value)
    _write_file(STORAGE, data)

def load(key):
    assert STORAGE is not None
    debug(f"storage: load: key: {key}")
    contents = _read_file(STORAGE)
    debug2(f"storage: load: contents: {contents}")
    data = contents["store"]
    debug2(f"storage: load: data: {data}")
    value = data.get(key, None)
    debug2(f"storage: load: wrapped value: {value}")
    if value is not None:
        value = _unwrap(value)
        debug(f"storage: load: value: {value}")
    return value
