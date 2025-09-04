import json
import time
import threading
import logging
import requests
from flask import Flask, render_template_string, request, redirect, url_for
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

PRODUCTS_FILE = "products.json"
CHECK_INTERVAL = 2  # seconds

# Telegram credentials
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Logger setup
logging.basicConfig(
    filename="apple_checker.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def load_products():
    try:
        with open(PRODUCTS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_products(products):
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(products, f, indent=4)


def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not set, skipping message")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")


def check_availability(product):
    url = (
        f"https://www.apple.com/in/shop/fulfillment-messages?fae=true&little=false"
        f"&parts.0={product['model']}&mts.0=regular&mts.1=sticky&fts=true"
    )
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        stores = data.get("body", {}).get("content", {}).get("pickupMessage", {}).get("stores", [])

        available = False
        for store in stores:
            parts = store.get("partsAvailability", {})
            if product["model"] in parts and parts[product["model"]]["pickupDisplay"] == "available":
                available = True
                break

        product["status"] = "Available" if available else "Not Available"

        if available and product.get("enabled", True):
            message = f"✅ {product['name']} ({product['model']}) is available for pickup!\n{product['link']}"
            send_telegram_message(message)
            logger.info(message)
        else:
            logger.info(f"Checked {product['name']} ({product['model']}): {product['status']}")

    except Exception as e:
        logger.error(f"Error checking availability for {product['model']}: {e}")
        product["status"] = "Error"


def background_checker():
    while True:
        products = load_products()
        changed = False
        for product in products:
            if product.get("enabled", True):
                check_availability(product)
                changed = True
        if changed:
            save_products(products)
        time.sleep(CHECK_INTERVAL)


@app.route("/")
def index():
    products = load_products()
    return render_template_string(TEMPLATE, products=products)


@app.route("/add", methods=["POST"])
def add_product():
    products = load_products()
    new_product = {
        "name": request.form["name"],
        "link": request.form["link"],
        "model": request.form["model"],
        "pincode": request.form["pincode"],
        "enabled": True,
        "status": "Unknown"
    }
    products.append(new_product)
    save_products(products)
    return redirect(url_for("index"))


@app.route("/delete/<path:model>", methods=["POST"])
def delete_product(model):
    products = load_products()
    products = [p for p in products if p["model"] != model]
    save_products(products)
    logger.info(f"Deleted product {model}")
    return redirect(url_for("index"))


@app.route("/toggle/<path:model>", methods=["POST"])
def toggle_product(model):
    products = load_products()
    for p in products:
        if p["model"] == model:
            p["enabled"] = not p.get("enabled", True)
            logger.info(f"Toggled {model} → {p['enabled']}")
            break
    save_products(products)
    return redirect(url_for("index"))


# HTML Template as string
TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Apple Store Pickup Bot</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
</head>
<body class="bg-light">
<div class="container mt-4">
  <h2 class="mb-4">🍏 Apple Store Pickup Bot</h2>

  <form method="post" action="{{ url_for('add_product') }}" class="row g-3 mb-4">
    <div class="col-md-3"><input class="form-control" name="name" placeholder="Product Name" required></div>
    <div class="col-md-3"><input class="form-control" name="link" placeholder="Product Link" required></div>
    <div class="col-md-2"><input class="form-control" name="model" placeholder="Model No." required></div>
    <div class="col-md-2"><input class="form-control" name="pincode" placeholder="Pincode" required></div>
    <div class="col-md-2"><button class="btn btn-primary w-100">Add Product</button></div>
  </form>

  <table class="table table-bordered table-hover bg-white shadow-sm">
    <thead class="table-dark">
      <tr>
        <th>Name</th>
        <th>Model</th>
        <th>Pincode</th>
        <th>Status</th>
        <th>Link</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>
      {% for p in products %}
      <tr>
        <td>{{ p['name'] }}</td>
        <td>{{ p['model'] }}</td>
        <td>{{ p['pincode'] }}</td>
        <td>
          {% if p['status'] == "Available" %}
            <span class="badge bg-success">{{ p['status'] }}</span>
          {% elif p['status'] == "Not Available" %}
            <span class="badge bg-danger">{{ p['status'] }}</span>
          {% else %}
            <span class="badge bg-secondary">{{ p['status'] }}</span>
          {% endif %}
        </td>
        <td><a href="{{ p['link'] }}" target="_blank">View</a></td>
        <td>
          <form method="post" action="{{ url_for('toggle_product', model=p['model']) }}" style="display:inline">
            {% if p['enabled'] %}
              <button class="btn btn-sm btn-warning">Disable</button>
            {% else %}
              <button class="btn btn-sm btn-success">Enable</button>
            {% endif %}
          </form>
          <form method="post" action="{{ url_for('delete_product', model=p['model']) }}" style="display:inline" onsubmit="return confirm('Delete this product?')">
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


if __name__ == "__main__":
    threading.Thread(target=background_checker, daemon=True).start()
    app.run(host="0.0.0.0", port=5001, debug=True)
