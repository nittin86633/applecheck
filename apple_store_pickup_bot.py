#!/usr/bin/env python3
"""
Apple Store Pickup Checker (India)

PIN code is fixed to 110001 (Delhi).
Model numbers/SKUs will be read from a config file (models.txt).

Usage:
    python apple_store_pickup_bot.py

Config file format (models.txt):
    Each line should contain one model number/SKU, e.g.:
    MPXV3HN/A
    MKU63HN/A

Note: This script calls Apple's website just like a browser would. Please use
it responsibly and avoid aggressive polling.
"""
from __future__ import annotations

import json
import sys
from typing import Dict, List, Any

import requests

# Fixed to India store
BASE_URL = "https://www.apple.com/in/shop/fulfillment-messages"
PINCODE = "110001"  # Fixed pincode
CONFIG_FILE = "models.txt"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.apple.com/",
}


def load_models(config_file: str = CONFIG_FILE) -> List[str]:
    """Load model numbers from a config file."""
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            models = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        return models
    except FileNotFoundError:
        print(f"Config file '{config_file}' not found. Please create it and add model SKUs.")
        sys.exit(1)


def fetch_availability(pincode: str, models: List[str], timeout: int = 20) -> Dict[str, Any]:
    params = {
        "searchNearby": "true",
        "location": pincode,
        "pl": "true",
        "mt": "compact",
    }
    for idx, sku in enumerate(models):
        params[f"parts.{idx}"] = sku

    resp = requests.get(BASE_URL, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def parse_pickup_status(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        stores = data["body"]["content"]["pickupMessage"]["stores"]
    except Exception:
        stores = []

    results: List[Dict[str, Any]] = []

    for store in stores:
        store_num = store.get("storeNumber") or store.get("storeId")
        store_name = store.get("storeName") or store.get("name")
        city = store.get("city") or store.get("storeCity")
        distance = store.get("retailStore", {}).get("distance") or store.get("distance")
        per_sku = store.get("partsAvailability", {})
        for sku, info in per_sku.items():
            pickup_display = info.get("pickupDisplay") or info.get("pickupType")
            quote = info.get("pickupSearchQuote") or info.get("messageTypes", {}).get("availability", {}).get("storeSelectionEnabledMessage")
            results.append(
                {
                    "storeNumber": store_num,
                    "storeName": store_name,
                    "city": city,
                    "distance": distance,
                    "model": sku,
                    "pickupDisplay": str(pickup_display).lower() if isinstance(pickup_display, str) else pickup_display,
                    "quote": quote,
                }
            )

    return results


def check(pincode: str, models: List[str]) -> List[Dict[str, Any]]:
    data = fetch_availability(pincode, models)
    rows = parse_pickup_status(data)

    wanted = set(models)
    priority = {"available": 0, "available_today": 0, "in_stock": 0, "unavailable": 1, None: 2}
    rows = [r for r in rows if r.get("model") in wanted]
    rows.sort(key=lambda r: (priority.get(r.get("pickupDisplay"), 1), r.get("distance") or 1e9))
    return rows


def main():
    models = load_models()
    if not models:
        print("No models found in config file.")
        return 1

    try:
        rows = check(PINCODE, models)

        if not rows:
            print("No nearby Apple Stores returned for this PIN/model combination.")
            return 1

        widths = {
            "store": 26,
            "city": 14,
            "model": 14,
            "status": 12,
        }
        header = f"{'Store':{widths['store']}}  {'City':{widths['city']}}  {'Model':{widths['model']}}  {'Status':{widths['status']}}  Message"
        print(header)
        print("-" * len(header))
        for r in rows:
            store = f"{r.get('storeName') or ''} ({r.get('storeNumber') or ''})"
            city = r.get("city") or ""
            model = r.get("model") or ""
            status = (r.get("pickupDisplay") or "").upper()
            msg = r.get("quote") or ""
            print(f"{store:{widths['store']}}  {city:{widths['city']}}  {model:{widths['model']}}  {status:{widths['status']}}  {msg}")

        return 0
    except requests.HTTPError as e:
        print(f"HTTP error: {e}")
        if e.response is not None:
            try:
                print(e.response.text[:400])
            except Exception:
                pass
        return 2
    except Exception as e:
        print(f"Error: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
