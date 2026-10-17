"""Shared configuration loader.

`config.json` holds neutral defaults and is committed; `config.local.json` holds
machine- and person-specific values and is git-ignored. The local file is merged
on top, key by key, so it only needs to carry what differs.

    from noosconf import conf, path
    conf("memory.max_facts", 100)
    path("memory.db")            # absolute Path, resolved against the repo root
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _merge(base, over):
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def _load():
    data = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    local = ROOT / "config.local.json"
    if local.exists():
        _merge(data, json.loads(local.read_text(encoding="utf-8")))
    return data


DATA = _load()


def conf(dotted, default=None):
    """conf("probes.loe.queue") -> value, or `default` if the key is absent."""
    node = DATA
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def path(dotted, default=None):
    """Same as conf(), but returns an absolute Path (~ expanded, relative to ROOT)."""
    value = conf(dotted, default)
    if value is None:
        return None
    p = Path(os.path.expanduser(str(value)))
    return p if p.is_absolute() else ROOT / p
