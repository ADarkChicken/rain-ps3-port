"""Loads PS3 crypto constants from tools/keys.local.json (never committed; see keys.example.json)."""
import json, os
_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys.local.json")
_K = None
def key(name):
    global _K
    if _K is None:
        if not os.path.exists(_PATH):
            raise SystemExit(f"Missing {_PATH}: copy keys.example.json to keys.local.json and fill it (see its _comment).")
        _K = json.load(open(_PATH))
    v = _K.get(name, "")
    if not v: raise SystemExit(f"keys.local.json: '{name}' is empty")
    return bytes.fromhex(v)
