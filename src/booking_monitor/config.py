from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class Settings:
    request_timeout_seconds: int = 20
    fetch_retries: int = 3
    missing_threshold: int = 3
    tombstone_days: int = 30


@dataclass(slots=True)
class PropertyConfig:
    id: str
    name: str
    calendar_url: str
    source: str | None = None


@dataclass(slots=True)
class MonitorConfig:
    settings: Settings
    properties: list[PropertyConfig]


def load_config(path: str | Path) -> MonitorConfig:
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text()) or {}

    settings_data = raw.get("settings", {})
    properties_data = raw.get("properties", [])
    if not properties_data:
        raise ValueError("config must define at least one property")

    settings = Settings(
        request_timeout_seconds=_int_value(settings_data, "request_timeout_seconds", 20),
        fetch_retries=_int_value(settings_data, "fetch_retries", 3),
        missing_threshold=_int_value(settings_data, "missing_threshold", 3),
        tombstone_days=_int_value(settings_data, "tombstone_days", 30),
    )

    properties: list[PropertyConfig] = []
    seen_ids: set[str] = set()
    for item in properties_data:
        property_id = _required_str(item, "id")
        if property_id in seen_ids:
            raise ValueError(f"duplicate property id: {property_id}")
        seen_ids.add(property_id)

        properties.append(
            PropertyConfig(
                id=property_id,
                name=_required_str(item, "name"),
                calendar_url=_required_str(item, "calendar_url"),
                source=_optional_str(item, "source"),
            )
        )

    return MonitorConfig(settings=settings, properties=properties)


def _required_str(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_str(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string when set")
    value = value.strip()
    return value or None


def _int_value(item: dict[str, Any], key: str, default: int) -> int:
    value = item.get(key, default)
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value
