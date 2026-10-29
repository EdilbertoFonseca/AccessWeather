from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .config import data_dir


SCHEMA_VERSION = 4


def _parse_moment(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class ForecastCache:
    """Guarda as respostas cruas do Open-Meteo para abrir a janela offline."""

    def __init__(self, path: Path | None = None, minutes=15):
        self.path = path or data_dir() / "cache.json"
        self.minutes = max(0, int(minutes))
        self.entries: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(loaded, dict):
            return
        try:
            version = int(loaded.get("version") or 0)
        except (TypeError, ValueError):
            version = 0
        if version != SCHEMA_VERSION:
            # Payloads de versões antigas podem não ter os campos atuais.
            return
        entries = loaded.get("entries")
        if not isinstance(entries, dict):
            return
        self.entries = {}
        for key, item in entries.items():
            if not isinstance(item, dict):
                continue
            payload = item.get("payload")
            if not isinstance(payload, dict):
                continue
            self.entries[str(key)] = {
                "fetched_at": str(item.get("fetched_at") or ""),
                "payload": payload,
            }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": SCHEMA_VERSION, "entries": self.entries}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(temporary, self.path)

    def set(self, key, payload, now=None) -> None:
        moment = now or datetime.now()
        self.entries[str(key)] = {
            "fetched_at": moment.replace(microsecond=0).isoformat(),
            "payload": payload,
        }

    def peek(self, key):
        entry = self.entries.get(str(key))
        return entry["payload"] if entry else None

    def age_seconds(self, key, now=None):
        entry = self.entries.get(str(key))
        if entry is None:
            return None
        fetched = _parse_moment(entry.get("fetched_at"))
        if fetched is None:
            return None
        reference = now or datetime.now()
        return (reference - fetched).total_seconds()

    def is_fresh(self, key, now=None) -> bool:
        age = self.age_seconds(key, now)
        return age is not None and age <= self.minutes * 60

    def get(self, key, now=None):
        """Payload somente se ainda estiver dentro do prazo de validade."""
        return self.peek(key) if self.is_fresh(key, now) else None

    def drop(self, key) -> bool:
        return self.entries.pop(str(key), None) is not None

    def prune(self, keep_keys) -> int:
        keep = {str(key) for key in keep_keys}
        before = len(self.entries)
        self.entries = {
            key: entry for key, entry in self.entries.items() if key in keep
        }
        return before - len(self.entries)

    def clear(self) -> None:
        self.entries = {}

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, key) -> bool:
        return str(key) in self.entries
