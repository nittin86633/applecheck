from flask import Flask, render_template, request, redirect, url_for
import json, os, requests, threading, time
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

PRODUCTS_FILE = "products.json"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ---------------- Utility ----------------
def load_products():
    if not os.path.exists(PRODUCTS_FILE):
        return []
    with open(PRODUCTS_FILE, "r") as f:
        return json.load(f)

def save_products(products):
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(products, f, indent=2)

def check_availability(product):
    try:
        url = (
            f"https://www.apple.com/in/shop/fulfillment-messages"
            f"?fae=true&little=false&parts.0={product['model']}&mts.0=regular&fts=true"
        )
        response = requests.get(url).json()
        stores = response.get("body", {}).get("content", {}).get("pickupMessage", {}).get("stores", [])
        if not stores:
            return "❌ Not Available"
        available = any(
            store.get("partsAvailability", {})
                 .get(product['model'], {})
                 .get("pickupDisplay") == "available"
            for store in stores
        )
        return "✅ Available" if available else "❌ Not Available"
    except Exception as e:
        return f"Error: {e}"

def send_telegram_message(text):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": text,
                "parse_mode": "HTML"
            }
        )
    except Exception as e:
        print("Telegram error:", e)

# ---------------- Background Checker ----------------
last_status = {}

def background_checker():
    global last_status
    while True:
        products = load_products()
        for p in products:
            if not p.get("enabled", True):
                continue

            status = check_availability(p)
            if status == "✅ Available" and last_status.get(p["model"]) != "✅ Available":
                message = (
                    f"📢 <b>{p['name']}</b> is now <b>Available</b>!\n\n"
                    f"🔗 {p['link']}\n"
                    f"📦 Model: {p['model']}\n"
                    f"📍 Pincode: {p['pincode']}"
                )
                send_telegram_message(message)

            last_status[p["model"]] = status

        time.sleep(2)

# ---------------- Routes ----------------
@app.route("/")
def index():
    products = load_products()
    for p in products:
        if p.get("enabled", True):
            p["status"] = check_availability(p)
        else:
            p["status"] = "⏸ Disabled"
    return render_template("index.html", products=products)

@app.route("/add", methods=["POST"])
def add_product():
    products = load_products()
    new_product = {
        "name": request.form["name"],
        "model": request.form["model"],
        "link": request.form["link"],
        "pincode": request.form["pincode"],
        "enabled": True
    }
    products.append(new_product)
    save_products(products)
    return redirect(url_for("index"))

@app.route("/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    products = load_products()
    if 0 <= product_id < len(products):
        products.pop(product_id)
        save_products(products)
    return redirect(url_for("index"))

@app.route("/toggle/<int:product_id>", methods=["POST"])
def toggle_product(product_id):
    products = load_products()
    if 0 <= product_id < len(products):
        products[product_id]["enabled"] = not products[product_id].get("enabled", True)
        save_products(products)
    return redirect(url_for("index"))

# ---------------- Run ----------------
if __name__ == "__main__":
    threading.Thread(target=background_checker, daemon=True).start()
    app.run(host="0.0.0.0", port=5001, debug=True)
