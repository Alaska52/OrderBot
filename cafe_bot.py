import logging
import random
import os
import csv
from pathlib import Path
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------
# Paths (absolute, reliable)
# ---------------------------
BASE_DIR = Path(__file__).resolve().parent
ORDERS_DIR = BASE_DIR / "orders"
ORDERS_CSV = ORDERS_DIR / "orders.csv"
ASSETS_DIR = BASE_DIR / "assets"
PAYNOW_QR = ASSETS_DIR / "paynow_qr.jpg"


# ---------------------------
# Conversation States
# ---------------------------
COFFEE_TYPE, VARIETY, ADDONS, REVIEW, PAYMENT = range(5)


# ---------------------------
# Menu
# ---------------------------
MENU = {
    "Matcha": {
        "varieties": {
            "Iced Matcha": 7.00,
            "Strawberry Matcha": 8.00,
        }
    },
    "Coffee": {
        "varieties": {
            "Iced Black": 4.50,
            "Ice White": 5.50,
        }
    },
    "Bakes": {
        "varieties": {
            "Banana Bread": 4.00,
            "Earl Grey Madeleines(4pcs)": 5.00,
            "Matcha Madeleines(4pcs)": 6.00,
        }
    },
}

ADDONS_MENU = {
    "Oat Milk": 1.00,
    "Extra Espresso Shot": 1.00,
    "Normal Sugar": 0.00,
    "Kosong (No Sugar)": 0.00,
    "Siew Dai (Less Sugar)": 0.00,
}


# ---------------------------
# CSV Helpers
# ---------------------------
def load_orders_rows():
    """Return (header, rows). rows excludes header. If missing/empty -> (None, [])."""
    if not ORDERS_CSV.exists():
        return None, []

    with ORDERS_CSV.open("r", encoding="utf-8", newline="") as f:
        all_rows = list(csv.reader(f))

    if len(all_rows) < 2:
        return (all_rows[0] if all_rows else None), []

    return all_rows[0], all_rows[1:]


def save_orders_rows(header, rows):
    ORDERS_DIR.mkdir(parents=True, exist_ok=True)
    with ORDERS_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if header:
            w.writerow(header)
        w.writerows(rows)


def get_status(row):
    return row[8] if len(row) > 8 and row[8] else "pending"


def set_status(row, status):
    while len(row) < 9:
        row.append("")
    row[8] = status


# ---------------------------
# Pricing
# ---------------------------
def calc_addon_price(addons: list[str]) -> float:
    total = 0.0
    for a in addons:
        if a in ADDONS_MENU:
            total += float(ADDONS_MENU[a])
        else:
            logger.warning("Unknown addon '%s' not found in ADDONS_MENU", a)
    return total


# ---------------------------
# User Flow
# ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    context.user_data["cart"] = []

    welcome_text = (
        "☕ *Welcome to Kristy Krib's Home Cafe!*\n\n"
        "📋 *Our Menu:*\n\n"
        "*Matcha Drinks:*\n"
        "• Iced Matcha - $7.00\n"
        "• Strawberry Matcha - $8.00\n"
        "*Coffee:*\n"
        "• Iced Black - $4.50\n"
        "• Ice White - $5.50\n"
        "*Fresh Bakes:*\n"
        "• Banana Bread - $4.00\n"
        "• Earl Grey Madeleines - $5.00\n"
        "• Matcha Madeleines - $6.00\n\n"
        "🥛 *Add-ons:*\n"
        "• Oat Milk (+$1.00)\n"
        "• Add Espresso Shot (+$1.00)\n"
        "• Sugar options (Normal/Kosong/Siew Dai)\n\n"
        "Let's start your order! 👇"
    )

    keyboard = [[InlineKeyboardButton(t, callback_data=f"type_{t}")] for t in MENU.keys()]

    await update.message.reply_text(
        welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return COFFEE_TYPE


async def coffee_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    ctype = query.data.replace("type_", "", 1)
    context.user_data["current"] = {"type": ctype, "addons": [], "temp": "N/A"}

    varieties = MENU[ctype]["varieties"]
    keyboard = [
        [InlineKeyboardButton(f"{name} - ${price:.2f}", callback_data=f"var_{name}")]
        for name, price in varieties.items()
    ]

    await query.edit_message_text(
        f"You selected: {ctype}\n\nChoose your item:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return VARIETY


async def variety_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    variety = query.data.replace("var_", "", 1)
    curr = context.user_data["current"]
    curr["variety"] = variety

    ctype = curr["type"]
    base_price = MENU[ctype]["varieties"][variety]
    curr["base_price"] = float(base_price)

    # If Bakes: skip addons
    if ctype == "Bakes":
        curr["temp"] = "N/A"
        curr["price"] = float(base_price)
        context.user_data["cart"].append(curr.copy())

        total = sum(float(item["price"]) for item in context.user_data["cart"])
        summary = "📋 Your Cart:\n\n"
        for i, item in enumerate(context.user_data["cart"], 1):
            summary += f"{i}. {item['variety']}\n"
            summary += f"   ${float(item['price']):.2f}\n\n"
        summary += f"Total: ${total:.2f}"

        keyboard = [
            [InlineKeyboardButton("➕ Add Another Item", callback_data="add_more")],
            [InlineKeyboardButton("💳 Proceed to Checkout", callback_data="checkout")],
        ]
        await query.edit_message_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
        return REVIEW

    # Drinks: show addons
    keyboard = []
    for addon, price in ADDONS_MENU.items():
        price_text = f" (+${price:.2f})" if price > 0 else ""
        keyboard.append([InlineKeyboardButton(f"{addon}{price_text}", callback_data=f"addon_{addon}")])

    keyboard.append([InlineKeyboardButton("✅ Done with add-ons", callback_data="addon_done")])

    await query.edit_message_text(
        f"Great choice! {variety} (${base_price:.2f})\n\n"
        "Select add-ons (tap multiple if needed):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ADDONS


async def addon_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    curr = context.user_data["current"]
    data = query.data or ""

    # Done selecting add-ons
    if data == "addon_done":
        base_price = float(curr.get("base_price", 0.0))
        addon_price = calc_addon_price(curr.get("addons", []))
        curr["addon_price"] = addon_price
        curr["price"] = base_price + addon_price

        context.user_data["cart"].append(curr.copy())

        total = sum(float(item["price"]) for item in context.user_data["cart"])
        summary = "📋 Your Cart:\n\n"
        for i, item in enumerate(context.user_data["cart"], 1):
            addons_text = ", ".join(item.get("addons", [])) if item.get("addons") else "None"
            summary += f"{i}. {item['variety']}\n"
            summary += f"   {item.get('temp','N/A')} {item['type']}\n"
            summary += f"   Add-ons: {addons_text}\n"
            summary += f"   Item Total: ${float(item['price']):.2f}\n\n"
        summary += f"Total: ${total:.2f}"

        keyboard = [
            [InlineKeyboardButton("➕ Add Another Item", callback_data="add_more")],
            [InlineKeyboardButton("💳 Proceed to Checkout", callback_data="checkout")],
        ]
        await query.edit_message_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
        return REVIEW

    # Selecting an add-on
    if data.startswith("addon_"):
        addon = data.replace("addon_", "", 1)
        if addon not in curr["addons"]:
            curr["addons"].append(addon)

    # LIVE subtotal display
    base_price = float(curr.get("base_price", 0.0))
    addon_price = calc_addon_price(curr.get("addons", []))
    item_total = base_price + addon_price
    addons_text = ", ".join(curr["addons"]) if curr["addons"] else "None"

    keyboard = []
    for name, price in ADDONS_MENU.items():
        price_text = f" (+${price:.2f})" if price > 0 else ""
        keyboard.append([InlineKeyboardButton(f"{name}{price_text}", callback_data=f"addon_{name}")])
    keyboard.append([InlineKeyboardButton("✅ Done with add-ons", callback_data="addon_done")])

    await query.edit_message_text(
        f"Add-ons selected: {addons_text}\n"
        f"Base: ${base_price:.2f}\n"
        f"Add-ons: ${addon_price:.2f}\n"
        f"Current item total: ${item_total:.2f}\n\n"
        "Tap more add-ons or press ✅ Done.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ADDONS


async def review_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "add_more":
        keyboard = [[InlineKeyboardButton(t, callback_data=f"type_{t}")] for t in MENU.keys()]
        await query.edit_message_text("Select your coffee type:", reply_markup=InlineKeyboardMarkup(keyboard))
        return COFFEE_TYPE

    # checkout
    username = query.from_user.username or query.from_user.first_name or "Customer"
    order_number = random.randint(100, 999)
    order_id = f"{username}_{order_number}"
    context.user_data["order_id"] = order_id

    total = sum(float(item["price"]) for item in context.user_data["cart"])

    await query.edit_message_text(
        f"Order ID: #{order_id}\n"
        f"Total Amount: ${total:.2f}\n\n"
        "Please make payment via PayNow and send:\n"
        "• Screenshot of payment, OR\n"
        "• Type 'PAID' to confirm\n\n"
        "QR code will be sent in next message..."
    )

    if PAYNOW_QR.exists():
        with PAYNOW_QR.open("rb") as photo:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo,
                caption=f"💳 Scan to pay ${total:.2f}\nOrder #{order_id}",
            )
    else:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                "⚠️ QR code image not found.\n"
                f"Expected: {PAYNOW_QR}\n\n"
                f"Amount to pay: ${total:.2f}"
            ),
        )

    return PAYMENT


async def payment_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    has_text = update.message.text and "PAID" in update.message.text.upper()
    has_photo = bool(update.message.photo)

    if not (has_text or has_photo):
        await update.message.reply_text("Please send a payment screenshot or type 'PAID' to confirm.")
        return PAYMENT

    order_id = context.user_data.get("order_id", "N/A")
    customer_name = update.effective_user.first_name or "Customer"
    customer_username = update.effective_user.username or "N/A"
    customer_id = update.effective_user.id

    save_order_to_file(order_id, customer_name, customer_username, customer_id, context.user_data["cart"])

    await update.message.reply_text(
        f"✅ Payment received!\n\n"
        f"Order ID: #{order_id}\n"
        f"Your order is being prepared.\n\n"
        f"Thank you for ordering from Home Cafe! ☕\n\n"
        f"Type /start to place a new order."
    )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Order cancelled.\n\nType /start to begin a new order.")
    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------
# Save order
# ---------------------------
def save_order_to_file(order_id, customer_name, customer_username, customer_id, cart):
    ORDERS_DIR.mkdir(parents=True, exist_ok=True)

    total = sum(float(item["price"]) for item in cart)
    items_text = "; ".join(
        [
            f"{item['variety']} ({item.get('temp','N/A')}) - Add-ons: {', '.join(item.get('addons', [])) if item.get('addons') else 'None'}"
            for item in cart
        ]
    )

    is_new_file = not ORDERS_CSV.exists() or ORDERS_CSV.stat().st_size == 0

    from datetime import datetime
    now = datetime.now()

    with ORDERS_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow(
                ["Order ID", "Date", "Time", "Customer Name", "Username", "User ID", "Items", "Total", "Status"]
            )

        writer.writerow(
            [
                order_id,
                now.strftime("%Y-%m-%d"),
                now.strftime("%H:%M:%S"),
                customer_name,
                f"@{customer_username}" if customer_username != "N/A" else "N/A",
                str(customer_id),
                items_text,
                f"${total:.2f}",
                "pending",
            ]
        )


# ---------------------------
# Admin commands: orders/today/pending
# ---------------------------
async def view_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    header, rows = load_orders_rows()
    if not rows:
        await update.message.reply_text("No orders yet!")
        return

    orders = rows[-10:]
    msg = "📋 *Recent Orders:*\n\n"
    for r in reversed(orders):
        order_id = r[0]
        date = r[1] if len(r) > 1 else ""
        time = r[2] if len(r) > 2 else ""
        customer = r[3] if len(r) > 3 else "Customer"
        total = r[7] if len(r) > 7 else ""
        status = get_status(r)
        status_emoji = "✅" if status == "ready" else "⏳"
        msg += f"{status_emoji} *{order_id}* - {date} {time}\n"
        msg += f"Customer: {customer}\n"
        msg += f"Total: {total}\n\n"

    await update.message.reply_text(msg, parse_mode="Markdown")


async def today_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime

    header, rows = load_orders_rows()
    if not rows:
        await update.message.reply_text("No orders yet!")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    today_rows = [r for r in rows if len(r) > 1 and r[1] == today]

    if not today_rows:
        await update.message.reply_text("No orders today yet!")
        return

    total_sales = 0.0
    for r in today_rows:
        if len(r) > 7 and r[7].startswith("$"):
            try:
                total_sales += float(r[7].replace("$", ""))
            except ValueError:
                pass

    msg = f"📊 *Today's Summary ({today})*\n\n"
    msg += f"Orders: {len(today_rows)}\n"
    msg += f"Total Sales: ${total_sales:.2f}\n\n"
    msg += "*Orders:*\n"

    for r in today_rows:
        oid = r[0]
        customer = r[3] if len(r) > 3 else "Customer"
        total = r[7] if len(r) > 7 else ""
        status = get_status(r)
        status_emoji = "✅" if status == "ready" else "⏳"
        msg += f"{status_emoji} {oid} - {customer} - {total}\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def view_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    header, rows = load_orders_rows()
    if not rows:
        await update.message.reply_text("No orders yet!")
        return

    text, markup = build_pending_message(rows)

    # Only pass reply_markup if it exists
    if markup:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

async def pending_buttons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    # Refresh
    if data == "pending:refresh":
        header, rows = load_orders_rows()
        text, markup = build_pending_message(rows)

        if markup:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        else:
            await query.edit_message_text(text, parse_mode="Markdown")
        return

    # Mark ready
    if data.startswith("ready:"):
        order_id = data.split("ready:", 1)[1]

        header, rows = load_orders_rows()
        if not rows:
            await query.edit_message_text("No orders found!")
            return

        found_index = None
        for i, r in enumerate(rows):
            if len(r) > 0 and r[0] == order_id and get_status(r) == "pending":
                found_index = i
                break

        if found_index is None:
            await query.answer("Order not found or already ready.", show_alert=True)
            return

        row = rows[found_index]
        set_status(row, "ready")
        rows[found_index] = row
        save_orders_rows(header, rows)

        # Notify customer
        customer_name = row[3] if len(row) > 3 else "Customer"
        customer_chat_id = row[5] if len(row) > 5 else None

        notify_error = None
        if customer_chat_id:
            try:
                await context.bot.send_message(
                    chat_id=int(customer_chat_id),
                    text=(
                        f"☕ Good news, {customer_name}!\n\n"
                        f"Your order #{order_id} is ready for collection! 🎉\n\n"
                        f"Please come pick it up. Thank you!"
                    ),
                )
            except Exception as e:
                notify_error = str(e)

        # Refresh list (WITH DETAILS)
        header, rows = load_orders_rows()
        text, markup = build_pending_message(rows)

        confirm = f"✅ Marked `{order_id}` as READY.\n"
        if notify_error:
            confirm += f"⚠️ Notify failed: {notify_error}\n"
        confirm += "\n"

        final_text = confirm + text

        if markup:
            await query.edit_message_text(final_text, parse_mode="Markdown", reply_markup=markup)
        else:
            await query.edit_message_text(final_text, parse_mode="Markdown")
        return

MAX_PENDING_SHOW = 10  # show full details for this many pending orders (avoid Telegram 4096 limit)

def format_items_multiline(items_text: str) -> str:
    """Convert the CSV 'Items' field into bullet lines."""
    items_text = (items_text or "").strip()
    if not items_text:
        return "   • (no items recorded)"

    parts = [p.strip() for p in items_text.split(";") if p.strip()]
    if not parts:
        return f"   • {items_text}"

    return "\n".join([f"   • {p}" for p in parts])

def build_pending_message(rows):
    """
    Returns (text, keyboard) for pending orders view.
    Keeps your existing callback_data: ready:<order_id> and pending:refresh.
    """
    pending = [r for r in rows if get_status(r) == "pending"]

    if not pending:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="pending:refresh")]])
        return "✅ No pending orders! All caught up!", keyboard


    shown = pending[:MAX_PENDING_SHOW]

    text = "⏳ *Pending Orders* (tap a button to mark READY)\n\n"

    keyboard = []
    for idx, r in enumerate(shown, 1):
        order_id = r[0] if len(r) > 0 else "UNKNOWN"
        date = r[1] if len(r) > 1 else ""
        time = r[2] if len(r) > 2 else ""
        customer = r[3] if len(r) > 3 else "Customer"
        username = r[4] if len(r) > 4 else ""
        items = r[6] if len(r) > 6 else ""
        total = r[7] if len(r) > 7 else ""

        text += (
            f"*{idx})* `{order_id}`\n"
            f"👤 {customer} {username}\n"
            f"🕒 {date} {time}\n"
            f"💰 {total}\n"
            f"{format_items_multiline(items)}\n\n"
        )

        # keep your current behavior: clicking this marks ready + notifies customer
        keyboard.append([InlineKeyboardButton(f"✅ READY: {order_id}", callback_data=f"ready:{order_id}")])

    if len(pending) > MAX_PENDING_SHOW:
        text += f"_Showing {MAX_PENDING_SHOW} of {len(pending)} pending orders. Tap Refresh to update._\n"

    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="pending:refresh")])
    return text, InlineKeyboardMarkup(keyboard)

async def mark_ready(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual command fallback: /ready ORDER_ID"""
    if not context.args:
        await update.message.reply_text("Please specify order ID.\nUsage: /ready ORD12345")
        return

    order_id = context.args[0]
    header, rows = load_orders_rows()

    if not rows:
        await update.message.reply_text("No orders found!")
        return

    found = None
    for i, r in enumerate(rows):
        if r and r[0] == order_id and get_status(r) == "pending":
            found = i
            break

    if found is None:
        await update.message.reply_text(f"❌ Order {order_id} not found or already marked as ready.")
        return

    row = rows[found]
    set_status(row, "ready")
    rows[found] = row
    save_orders_rows(header, rows)

    customer_chat_id = row[5] if len(row) > 5 else None
    customer_name = row[3] if len(row) > 3 else "Customer"

    try:
        if customer_chat_id:
            await context.bot.send_message(
                chat_id=int(customer_chat_id),
                text=(
                    f"☕ Good news, {customer_name}!\n\n"
                    f"Your order #{order_id} is ready for collection! 🎉\n\n"
                    f"Please come pick it up. Thank you!"
                ),
            )
        await update.message.reply_text(f"✅ Order {order_id} marked as ready!")
    except Exception as e:
        await update.message.reply_text(f"✅ Order {order_id} marked as ready!\n⚠️ Could not notify customer: {e}")


# ---------------------------
# Error handler (shows why it "won't start")
# ---------------------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception:", exc_info=context.error)


# ---------------------------
# Main
# ---------------------------
def main() -> None:
    # Load dotenv reliably from script folder
    load_dotenv(BASE_DIR / ".env")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

    print("ptb script path:", BASE_DIR)
    print("orders csv path:", ORDERS_CSV)

    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN not found in .env next to this .py file")
        print(f"Expected .env at: {BASE_DIR / '.env'}")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_error_handler(on_error)

    # 1) Admin button callbacks FIRST (group 0)
    app.add_handler(CallbackQueryHandler(pending_buttons_callback, pattern=r"^ready:"), group=0)
    app.add_handler(CallbackQueryHandler(pending_buttons_callback, pattern=r"^pending:refresh$"), group=0)

    # 2) Ordering flow SECOND (group 1)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            COFFEE_TYPE: [CallbackQueryHandler(coffee_selected, pattern=r"^type_")],
            VARIETY:     [CallbackQueryHandler(variety_selected, pattern=r"^var_")],
            # IMPORTANT: include addon_done too
            ADDONS:      [CallbackQueryHandler(addon_selected, pattern=r"^(addon_.*|addon_done)$")],
            REVIEW:      [CallbackQueryHandler(review_action, pattern=r"^(add_more|checkout)$")],
            PAYMENT:     [MessageHandler(filters.TEXT | filters.PHOTO, payment_done)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler, group=1)

    # 3) Commands
    app.add_handler(CommandHandler("orders", view_orders))
    app.add_handler(CommandHandler("today", today_orders))
    app.add_handler(CommandHandler("pending", view_pending))
    app.add_handler(CommandHandler("ready", mark_ready))

    print("🤖 Bot is running... Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
