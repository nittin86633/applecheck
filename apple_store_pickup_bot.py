#!/usr/bin/env python3
"""
Apple Store Pickup Checker (India) - Web UI + Telegram Notifications
Runs on port 5001
"""

import os
import json
import threading
import requests
import logging
from flask import Flask, render_template_string, request, redirect, url_for

# ==========================
# Config
# ==========================
BASE_URL = "https://www.apple.com/in/shop/fulfillment-messages"
PRODUCTS_FILE = "products.json"

# Telegram config
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.apple.com/",
}

# In-memory cache for latest statuses
latest_status = {}

# ==========================
# Logging Setup
# ==========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("apple_checker.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ==========================
# Helpers
# ==========================
def load_products():
    if not os.path.exists(PRODUCTS_FILE):
        return []
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)


def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        logger.error(f"Telegram error: {e}")


def fetch_availability(pincode, model, timeout=20):
    params = {"searchNearby": "true", "location": pincode, "pl": "true", "mt": "compact"}
    params["parts.0"] = model
    resp = requests.get(BASE_URL, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def parse_pickup_status(data):
    try:
        stores = data["body"]["content"]["pickupMessage"]["stores"]
    except Exception:
        stores = []

    results = []
    for store in stores:
        store_name = store.get("storeName") or store.get("name")
        city = store.get("city") or store.get("storeCity")
        per_sku = store.get("partsAvailability", {})
        for sku, info in per_sku.items():
            pickup_display = info.get("pickupDisplay") or info.get("pickupType")
            quote = (
                info.get("pickupSearchQuote")
                or info.get("messageTypes", {}).get("availability", {}).get("storeSelectionEnabledMessage")
            )
            results.append(
                {
                    "store": store_name,
                    "city": city,
                    "model": sku,
                    "pickupDisplay": str(pickup_display).lower() if isinstance(pickup_display, str) else pickup_display,
                    "quote": quote,
                }
            )
    return results


# ==========================
# Background Checker
# ==========================
def background_checker():
    while True:
        products = load_products()
        for product in products:
            if not product.get("enabled", True):
                latest_status[product["model"]] = {"status": "disabled", "message": "Disabled by user"}
                logger.info(f"⏸ Skipped (disabled): {product['name']} ({product['model']})")
                continue

            try:
                logger.info(f"🔍 Checking: {product['name']} ({product['model']}) at {product['pincode']}")
                data = fetch_availability(product["pincode"], product["model"])
                rows = parse_pickup_status(data)

                product_status = "unavailable"
                product_msg = "No nearby stores found"

                for r in rows:
                    product_status = r["pickupDisplay"]
                    product_msg = f"{r['store']} ({r['city']}) → {r['pickupDisplay'].upper()} : {r['quote']}"
                    logger.info(f"📦 Result: {product_msg}")

                    if r["pickupDisplay"] == "available":
                        msg = f"✅ IN STOCK!\n{product['name']} ({product['model']})\n{product_msg}\n{product['link']}"
                        send_telegram_message(msg)
                        logger.info(f"📲 Telegram sent: {msg}")
                        break

                latest_status[product["model"]] = {"status": product_status, "message": product_msg}

            except Exception as e:
                latest_status[product["model"]] = {"status": "error", "message": str(e)}
                logger.error(f"❌ Error for {product['name']} ({product['model']}): {e}")

        # ⚡️ No sleep here — it immediately restarts checking loop


# ==========================
# Flask App
# ==========================
app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    products = load_products()

    if request.method == "POST":
        # Add new product
        name = request.form.get("name").strip()
        model = request.form.get("model").strip()
        link = request.form.get("link").strip()
        pincode = request.form.get("pincode").strip()
        products.append({"name": name, "model": model, "link": link, "pincode": pincode, "enabled": True})
        save_products(products)
        return redirect(url_for("index"))

    template = """
    <!doctype html>
    <html>
    <head>
        <title>Apple Pickup Checker</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
    </head>
    <body class="bg-light">
    <div class="container py-4">
        <h1 class="mb-4">🍎 Apple Store Pickup Checker (India)</h1>

        <div class="card mb-4">
            <div class="card-header">➕ Add New Product</div>
            <div class="card-body">
                <form method="post" class="row g-3">
                    <div class="col-md-3">
                        <input class="form-control" placeholder="Product Name" name="name" required>
                    </div>
                    <div class="col-md-3">
                        <input class="form-control" placeholder="Model No (SKU)" name="model" required>
                    </div>
                    <div class="col-md-3">
                        <input class="form-control" placeholder="Product Link" name="link" required>
                    </div>
                    <div class="col-md-2">
                        <input class="form-control" placeholder="Pincode" name="pincode" required>
                    </div>
                    <div class="col-md-1">
                        <button class="btn btn-primary w-100">Add</button>
                    </div>
                </form>
            </div>
        </div>

        <h2>📦 Saved Products</h2>
        <table class="table table-bordered table-hover bg-white">
            <thead class="table-light">
                <tr>
                    <th>Name</th>
                    <th>Model</th>
                    <th>Pincode</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
            {% for p in products %}
                {% set status = latest_status.get(p['model'], {}).get('status', 'checking') %}
                {% set message = latest_status.get(p['model'], {}).get('message', 'Checking...') %}
                <tr>
                    <td><a href="{{p['link']}}" target="_blank">{{p['name']}}</a></td>
                    <td>{{p['model']}}</td>
                    <td>{{p['pincode']}}</td>
                    <td>
                        {% if status == 'available' %}
                            <span class="badge bg-success">{{message}}</span>
                        {% elif status == 'unavailable' %}
                            <span class="badge bg-danger">{{message}}</span>
                        {% elif status == 'error' %}
                            <span class="badge bg-warning text-dark">{{message}}</span>
                        {% elif status == 'disabled' %}
                            <span class="badge bg-secondary">{{message}}</span>
                        {% else %}
                            <span class="badge bg-info text-dark">{{message}}</span>
                        {% endif %}
                    </td>
                    <td>
                        <form method="post" action="{{ url_for('toggle_product', model=p['model']) }}" style="display:inline">
                            {% if p['enabled'] %}
                                <button class="btn btn-sm btn-warning">Disable</button>
                            {% else %}
                                <button class="btn btn-sm btn-success">Enable</button>
                            {% endif %}
                        </form>
                        <form method="post" action="{{ url_for('delete_product', model=p['model']) }}" style="display:inline">
                            <button class="btn btn-sm btn-danger">Delete</button>
                        </form>
                    </td>
                </tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
    </body>
    </html>
    """
    return render_template_string(template, products=products, latest_status=latest_status)


@app.route("/delete/<path:model>", methods=["POST"])
def delete_product(model):
    products = load_products()
    products = [p for p in products if p["model"] != model]
    save_products(products)
    return redirect(url_for("index"))


@app.route("/toggle/<path:model>", methods=["POST"])
def toggle_product(model):
    products = load_products()
    for p in products:
        if p["model"] == model:
            p["enabled"] = not p.get("enabled", True)
    save_products(products)
    return redirect(url_for("index"))


# ==========================
# Run App
# ==========================
if __name__ == "__main__":
    threading.Thread(target=background_checker, daemon=True).start()
    app.run(host="0.0.0.0", port=5001, debug=True)
