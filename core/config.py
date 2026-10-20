"""Settings file (config.json): load with defaults filled in, save safely."""
import copy
import json
import os
import shutil


def merge(defaults, data):
    """Defaults with the saved values laid over them (nested dicts merged key by key)."""
    out = copy.deepcopy(defaults)
    for k, v in (data or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path, defaults):
    data = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("not a settings object")
    except FileNotFoundError:
        pass
    except Exception as e:
        broken = os.path.splitext(path)[0] + ".broken.json"
        print(f"config.json couldn't be read ({e}). Using default settings; "
              f"the old file was copied to {os.path.basename(broken)}.")
        try:
            shutil.copyfile(path, broken)
        except Exception:
            pass
        data = {}
    return merge(defaults, data)


def save(path, data):
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        print("Couldn't save config.json:", e)
