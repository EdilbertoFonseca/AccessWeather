from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from .config import (
    DEFAULT_NOTIFICATION_FIELDS,
    DEFAULT_NOTIFICATION_INTERVAL,
    data_dir,
    clamp_notification_interval,
    WEATHER_NOTIFICATION_FIELDS,
)
from .weather import Place, WeatherError


SCHEMA_VERSION = 1


@dataclass
class SavedLocation:
    """Um local guardado, com as opções que a UI e os alertas consultam."""

    place: Place
    alias: str = ""
    favorite: bool = False
    notify: bool = True
    alerts: tuple = field(default_factory=tuple)
    notify_hourly: bool = False
    notify_fields: tuple = field(default_factory=tuple)
    notify_interval: int = DEFAULT_NOTIFICATION_INTERVAL

    @property
    def key(self) -> str:
        return self.place.key

    @property
    def notification_fields(self) -> tuple:
        return self.notify_fields or DEFAULT_NOTIFICATION_FIELDS

    @property
    def display_name(self) -> str:
        return self.alias.strip() or self.place.name

    @property
    def full_label(self) -> str:
        if self.alias.strip() and self.alias.strip() != self.place.label:
            return f"{self.alias.strip()} ({self.place.label})"
        return self.place.label

    def to_dict(self) -> dict:
        return {
            "place": self.place.to_dict(),
            "alias": self.alias,
            "favorite": self.favorite,
            "notify": self.notify,
            "alerts": list(self.alerts),
            "notify_hourly": self.notify_hourly,
            "notify_fields": list(self.notify_fields),
            "notify_interval": self.notify_interval,
        }

    @classmethod
    def from_dict(cls, payload) -> "SavedLocation":
        if not isinstance(payload, dict):
            raise WeatherError("Local salvo inválido.")
        place = payload.get("place")
        if not isinstance(place, dict):
            # Aceita o formato antigo em que o local era o próprio objeto.
            place = payload
        alerts = payload.get("alerts")
        fields = payload.get("notify_fields")
        notify_fields = (
            tuple(str(item) for item in fields if item in WEATHER_NOTIFICATION_FIELDS)
            if isinstance(fields, list)
            else ()
        )
        return cls(
            place=Place.from_dict(place),
            alias=str(payload.get("alias") or ""),
            favorite=bool(payload.get("favorite", False)),
            notify=bool(payload.get("notify", True)),
            alerts=tuple(alerts) if isinstance(alerts, list) else (),
            notify_hourly=bool(payload.get("notify_hourly", False)),
            notify_fields=notify_fields,
            notify_interval=clamp_notification_interval(
                payload.get("notify_interval", DEFAULT_NOTIFICATION_INTERVAL)
            ),
        )

    def with_place(self, place: Place) -> "SavedLocation":
        return replace(self, place=place)


class LocationStore:
    """Lista ordenada de locais salvos, persistida em `data/locations.json`."""

    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "locations.json"
        self.locations: list[SavedLocation] = []
        self.default_key = ""
        self.load()

    def load(self) -> None:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(loaded, dict):
            return
        raw = loaded.get("locations")
        if not isinstance(raw, list):
            return
        saved = []
        seen = set()
        for item in raw:
            try:
                location = SavedLocation.from_dict(item)
            except WeatherError:
                continue
            if location.key in seen:
                continue
            seen.add(location.key)
            saved.append(location)
        self.locations = saved
        default = loaded.get("default")
        self.default_key = default if isinstance(default, str) else ""
        self._repair_default()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": SCHEMA_VERSION,
            "default": self.default_key,
            "locations": [location.to_dict() for location in self.locations],
        }
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, self.path)

    def _repair_default(self) -> None:
        if self.default_key and self.find(self.default_key) is None:
            self.default_key = ""
        if not self.default_key and self.locations:
            self.default_key = self.locations[0].key

    def find(self, key) -> SavedLocation | None:
        for location in self.locations:
            if location.key == key:
                return location
        return None

    def find_place(self, place: Place) -> SavedLocation | None:
        for location in self.locations:
            if location.key == place.key:
                return location
            if place.place_id and location.place.place_id == place.place_id:
                return location
        return None

    def add(self, place: Place, alias: str = "") -> SavedLocation:
        """Adiciona o local ou devolve o existente atualizando os dados dele."""
        alias = str(alias or "").strip()
        existing = self.find_place(place)
        if existing is not None:
            existing.place = place
            if alias:
                existing.alias = alias
            if not self.default_key:
                self.default_key = existing.key
            return existing
        location = SavedLocation(place=place, alias=alias)
        self.locations.append(location)
        if not self.default_key:
            self.default_key = location.key
        return location

    def remove(self, key) -> bool:
        before = len(self.locations)
        self.locations = [loc for loc in self.locations if loc.key != key]
        if len(self.locations) == before:
            return False
        if self.default_key == key or self.find(self.default_key) is None:
            self.default_key = self.locations[0].key if self.locations else ""
        return True

    def clear(self) -> None:
        self.locations = []
        self.default_key = ""

    def index_of(self, key) -> int:
        for index, location in enumerate(self.locations):
            if location.key == key:
                return index
        return -1

    def move(self, key, offset) -> bool:
        origin = self.index_of(key)
        if origin < 0:
            return False
        destination = max(0, min(len(self.locations) - 1, origin + int(offset)))
        if destination == origin:
            return False
        location = self.locations.pop(origin)
        self.locations.insert(destination, location)
        return True

    def move_to(self, key, index) -> bool:
        origin = self.index_of(key)
        if origin < 0:
            return False
        destination = max(0, min(len(self.locations) - 1, int(index)))
        if destination == origin:
            return False
        location = self.locations.pop(origin)
        self.locations.insert(destination, location)
        return True

    def reorder(self, keys) -> bool:
        wanted = [key for key in keys if self.find(key) is not None]
        if len(wanted) != len(self.locations):
            return False
        order = {key: index for index, key in enumerate(wanted)}
        self.locations.sort(key=lambda location: order[location.key])
        return True

    def set_alias(self, key, alias) -> bool:
        location = self.find(key)
        if location is None:
            return False
        location.alias = str(alias or "").strip()
        return True

    def set_favorite(self, key, value) -> bool:
        location = self.find(key)
        if location is None:
            return False
        location.favorite = bool(value)
        return True

    def toggle_favorite(self, key) -> bool:
        location = self.find(key)
        if location is None:
            return False
        location.favorite = not location.favorite
        return location.favorite

    def set_notify(self, key, value) -> bool:
        location = self.find(key)
        if location is None:
            return False
        location.notify = bool(value)
        return True

    def set_alerts(self, key, alerts) -> bool:
        location = self.find(key)
        if location is None:
            return False
        location.alerts = tuple(alerts or ())
        return True

    def set_notification(self, key, enabled, fields, interval=None) -> bool:
        location = self.find(key)
        if location is None:
            return False
        location.notify_hourly = bool(enabled)
        location.notify_fields = tuple(
            str(item) for item in (fields or ()) if item in WEATHER_NOTIFICATION_FIELDS
        )
        if interval is not None:
            location.notify_interval = clamp_notification_interval(interval)
        return True

    def set_default(self, key) -> bool:
        if self.find(key) is None:
            return False
        self.default_key = key
        return True

    @property
    def default(self) -> SavedLocation | None:
        if not self.locations:
            return None
        return self.find(self.default_key) or self.locations[0]

    @property
    def favorites(self) -> list[SavedLocation]:
        return [location for location in self.locations if location.favorite]

    def cycle(self, key, offset=1) -> SavedLocation | None:
        """Local seguinte/anterior na lista, em ciclo; usado pela troca rápida."""
        if not self.locations:
            return None
        origin = self.index_of(key)
        if origin < 0:
            return self.locations[0]
        return self.locations[(origin + int(offset)) % len(self.locations)]

    def keys(self) -> list[str]:
        return [location.key for location in self.locations]

    def __len__(self) -> int:
        return len(self.locations)

    def __iter__(self):
        return iter(self.locations)

    def __contains__(self, key) -> bool:
        return self.find(key) is not None