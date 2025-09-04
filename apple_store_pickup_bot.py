#!/usr/bin/env python3
"""
Apple Store Pickup Checker (India) - Web UI + Telegram Notifications
Runs on port 5001
"""

import os
import json
import time
import threading
import requests
from flask import Flask, render_template_string, request, redirect, url_for

# ==========================
# Config
# ==========================
BASE_URL = "https://www.apple.com/in/shop/fulfillment-messages"
PRODUCTS_FILE = "products.json"

# Telegram config (fill your values here)
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.apple.com/",
}

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
        print("Telegram error:", e)

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
            quote = info.get("pickupSearchQuote") or info.get("messageTypes", {}).get("availability", {}).get("storeSelectionEnabledMessage")
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
# Background Checker Thread
# ==========================
def background_checker():
    while True:
        products = load_products()
        for product in products:
            try:
                data = fetch_availability(product["pincode"], product["model"])
                rows = parse_pickup_status(data)
                for r in rows:
                    status = f"{product['name']} ({product['model']}) @ {r['store']} [{r['city']}] → {r['pickupDisplay'].upper()} : {r['quote']}\n{product['link']}"
                    print(status)
                    if r["pickupDisplay"] == "available":
                        send_telegram_message("✅ IN STOCK!\n" + status)
            except Exception as e:
                print("Error checking:", product, e)
            time.sleep(2)  # 2 second gap per product

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
        products.append({"name": name, "model": model, "link": link, "pincode": pincode})
        save_products(products)
        return redirect(url_for("index"))

    template = """
    <!doctype html>
    <html>
    <head>
        <title>Apple Pickup Checker</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            table { border-collapse: collapse; width: 100%; margin-top: 20px; }
            th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
            th { background: #f2f2f2; }
            .form-section { margin-bottom: 20px; padding: 10px; border: 1px solid #ccc; }
        </style>
    </head>
    <body>
        <h1>Apple Store Pickup Checker (India)</h1>
        <div class="form-section">
            <form method="post">
                <label>Product Name: <input type="text" name="name" required></label><br><br>
                <label>Model No (SKU): <input type="text" name="model" required></label><br><br>
                <label>Product Link: <input type="url" name="link" required></label><br><br>
                <label>Pincode: <input type="text" name="pincode" required></label><br><br>
                <button type="submit">Add Product</button>
            </form>
        </div>

        <h2>Saved Products</h2>
        <table>
            <tr>
                <th>Name</th>
                <th>Model</th>
                <th>Link</th>
                <th>Pincode</th>
            </tr>
            {% for p in products %}
            <tr>
                <td>{{p.name}}</td>
                <td>{{p.model}}</td>
                <td><a href="{{p.link}}" target="_blank">View</a></td>
                <td>{{p.pincode}}</td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    return render_template_string(template, products=products)

# ==========================
# Run App
# ==========================
if __name__ == "__main__":
    threading.Thread(target=background_checker, daemon=True).start()
    app.run(host="0.0.0.0", port=5001, debug=True)
