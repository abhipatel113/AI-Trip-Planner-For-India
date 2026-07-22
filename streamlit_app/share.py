

from __future__ import annotations

import base64
import json

SCHEMA_VERSION = 1


def encode_share(payload: dict) -> str:
    """Encode a share payload dict to a URL-safe base64 string."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_share(token: str) -> dict | None:
    """Decode a share token back into a payload dict, or None if invalid."""
    if not token:
        return None
    try:
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + pad)
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or data.get("v") != SCHEMA_VERSION:
        return None
    itin = data.get("itinerary")
    if not isinstance(itin, dict) or not isinstance(itin.get("days"), list):
        return None
    return data


def build_payload(
    itinerary: dict,
    city: str,
    days: int,
    budget: int,
    travel_style: str | None = None,
    diet: str | None = None,
) -> dict:
    return {
    "v": SCHEMA_VERSION,
    "city": city,
    "days": days,
    "budget": budget,
    "travelStyle": travel_style,
    "diet": diet,
    "itinerary": itinerary,
    }