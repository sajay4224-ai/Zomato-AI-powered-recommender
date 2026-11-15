from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.models import RestaurantCandidate

_MISSING_MARKERS = {
    "",
    "-",
    "--",
    "n/a",
    "na",
    "nan",
    "new",
    "none",
    "null",
    "unknown",
}


class DatasetIngestionError(RuntimeError):
    """Raised when the source dataset cannot be loaded or validated."""


@dataclass
class CatalogDiagnostics:
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    missing_name_rows: int = 0
    missing_city_rows: int = 0
    missing_cost_rows: int = 0
    missing_rating_rows: int = 0


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).strip().split())
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered in _MISSING_MARKERS:
        return None
    return cleaned


def _normalize_cuisines(value: object) -> list[str]:
    if value is None:
        return []
    pieces: list[str] = []
    seen: set[str] = set()
    for chunk in str(value).split(","):
        item = _normalize_text(chunk)
        if not item:
            continue
        lowered = item.lower()
        if lowered not in seen:
            pieces.append(item)
            seen.add(lowered)
    return pieces


def _parse_rating(value: object) -> float | None:
    text = _normalize_text(value)
    if text is None:
        return None
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*/\s*5", text, flags=re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if parsed < 0 or parsed > 5:
        return None
    return parsed


def _parse_cost(value: object) -> float | None:
    text = _normalize_text(value)
    if text is None:
        return None
    cleaned = text.replace(",", "").replace("₹", "").replace("Rs", "").replace("INR", "")
    cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
    if not cleaned or cleaned in {"-", "."}:
        return None
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    return parsed


def _stable_restaurant_id(name: str, city: str | None, address: str | None) -> str:
    raw = "|".join(
        [
            name.strip(),
            city.strip() if city else "",
            address.strip() if address else "",
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"restaurant-{digest}"


class RestaurantCatalog:
    def __init__(self, restaurants: list[RestaurantCandidate], catalog_version: str | None = None):
        self.restaurants = restaurants
        self.catalog_version = catalog_version or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.by_id = {restaurant.id: restaurant for restaurant in self.restaurants}

    @classmethod
    def empty(cls) -> "RestaurantCatalog":
        return cls([], catalog_version=None)

    @classmethod
    def from_csv_text(cls, csv_text: str, source_url: str | None = None) -> "RestaurantCatalog":
        if not csv_text or not csv_text.strip():
            raise DatasetIngestionError("The dataset source is empty.")

        csv.field_size_limit(max(csv.field_size_limit(), 10_000_000))
        reader = csv.DictReader(io.StringIO(csv_text))
        if reader.fieldnames is None:
            raise DatasetIngestionError("The dataset does not include a CSV header row.")

        restaurants: list[RestaurantCandidate] = []
        diagnostics = CatalogDiagnostics()
        seen_ids: set[str] = set()

        for row in reader:
            diagnostics.total_rows += 1
            record: dict[str, object] = {key: value for key, value in row.items() if key is not None}
            name = _normalize_text(record.get("name"))
            city = _normalize_text(record.get("listed_in(city)") or record.get("city"))
            if not name:
                diagnostics.invalid_rows += 1
                diagnostics.missing_name_rows += 1
                continue
            if not city:
                diagnostics.missing_city_rows += 1
            raw_cost = record.get("approx_cost(for two people)")
            raw_rating = record.get("rate")
            cost_value = _parse_cost(raw_cost)
            rating_value = _parse_rating(raw_rating)
            if cost_value is None:
                diagnostics.missing_cost_rows += 1
            if rating_value is None:
                diagnostics.missing_rating_rows += 1

            restaurant_id = _stable_restaurant_id(
                name,
                city,
                _normalize_text(record.get("address")) or _normalize_text(record.get("url")),
            )
            if restaurant_id in seen_ids:
                diagnostics.invalid_rows += 1
                continue
            seen_ids.add(restaurant_id)

            restaurant = RestaurantCandidate(
                id=restaurant_id,
                name=name,
                location=_normalize_text(record.get("location")),
                city=city,
                cuisines=_normalize_cuisines(record.get("cuisines") or record.get("dish_liked")),
                cost=cost_value,
                cost_display=(
                    _normalize_text(raw_cost)
                    if cost_value is not None
                    else None
                ),
                rating=rating_value,
                source_fields={
                    key: value
                    for key, value in record.items()
                    if key and value is not None and str(value).strip() not in {"", "-", "NEW", "N/A"}
                },
            )
            restaurants.append(restaurant)
            diagnostics.valid_rows += 1

        if not restaurants:
            raise DatasetIngestionError(
                "The dataset did not yield any valid restaurant records after normalization."
            )

        return cls(
            restaurants=restaurants,
            catalog_version=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    @classmethod
    def from_csv_url(cls, url: str) -> "RestaurantCatalog":
        if not url or not str(url).strip():
            raise DatasetIngestionError("DATASET_URL is required to load the restaurant catalog.")

        normalized_url = str(url).strip()
        if "://" in normalized_url:
            request = Request(normalized_url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urlopen(request, timeout=30) as response:
                    payload = response.read()
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                raise DatasetIngestionError(
                    f"Unable to fetch restaurant catalog from {normalized_url}: {exc}"
                ) from exc
        else:
            csv_path = Path(normalized_url)
            if not csv_path.exists():
                raise DatasetIngestionError(f"Restaurant catalog file not found: {csv_path}")
            payload = csv_path.read_bytes()

        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = payload.decode("latin-1")
            except UnicodeDecodeError as exc:
                raise DatasetIngestionError("Dataset encoding is not readable as UTF-8 or Latin-1.") from exc

        return cls.from_csv_text(text, source_url=normalized_url)

    def __len__(self) -> int:
        return len(self.restaurants)

    def get_restaurant(self, restaurant_id: str) -> RestaurantCandidate | None:
        return self.by_id.get(restaurant_id)
