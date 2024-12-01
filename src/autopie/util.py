
import sys

VERBOSE = 0

def set_verbose(level=1):
    global VERBOSE
    VERBOSE = level

def debug(m):
    if VERBOSE < 1:
        return
    print(f"DEBUG: {m}")

def trace(m):
    if VERBOSE < 2:
        return
    print(f"TRACE: {m}")

def info(m):
    print(f"INFO: {m}")

def warning(m):
    print(f"WARNING: {m}")

def warn(m):
    warning(m)

def error(m):
    print(f"ERROR: {m}")
    sys.exit(1)

def stop():
    print(f"STOP ... Execution halted for debugging purposes")
    sys.exit(100)

