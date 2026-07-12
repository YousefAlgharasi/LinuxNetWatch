"""Small per-user preferences file (e.g. last-selected time range)."""
import json
import os

PREFS_PATH = os.path.expanduser("~/.config/datapulse/prefs.json")


def load_prefs():
    try:
        with open(PREFS_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_prefs(prefs):
    os.makedirs(os.path.dirname(PREFS_PATH), exist_ok=True)
    with open(PREFS_PATH, "w") as f:
        json.dump(prefs, f)


def get_range(default="1h"):
    return load_prefs().get("range", default)


def set_range(range_key):
    prefs = load_prefs()
    prefs["range"] = range_key
    save_prefs(prefs)
