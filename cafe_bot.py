import logging
import random
import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s', level=logging.INFO)

# States
COFFEE_TYPE, TEMPERATURE, VARIETY, ADDONS, REVIEW, PAYMENT = range(6)

# Menu
MENU = {
    'Matcha': {
        'varieties': {
            'Iced Matcha': 7.00,
            'Strawberry Matcha': 8.00
        }
    },
    'Coffee': {
        'varieties': {
            'Iced Black': 4.50,
            'Ice White': 5.50
        }
    },
    'Bakes': {
        'varieties': {
            'Banana Bread': 4.00,
            'Earl Grey Madeleines(4pcs)': 5.00,
            'Matcha Madeleines(4pcs)': 6.00
        }
    }
}

TEMPS = ['Hot', 'Iced']
ADDONS_MENU = {
    'Oat Milk': 1.00,
    'Extra Expresso Shot': 1.00,
    'Normal Sugar': 0.00,
    'Kosong (No Sugar)': 0.00,
    'Siew Dai (Less Sugar)': 0.00
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start conversation and show coffee types."""
    context.user_data.clear()
    context.user_data['cart'] = []
    
    # Welcome message with menu info
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
        "• Fresh Milk (+$0.50)\n"
        "• Oat Milk (+$1.00)\n"
        "• Sugar options (Normal/Kosong/Siew Dai)\n\n"
        "Let's start your order! 👇"
    )
    
    keyboard = [[InlineKeyboardButton(t, callback_data=f"type_{t}")] for t in MENU.keys()]
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return COFFEE_TYPE

async def coffee_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle coffee type selection."""
    query = update.callback_query
    await query.answer()
    
    ctype = query.data.replace("type_", "")
    context.user_data['current'] = {'type': ctype, 'addons': []}
    
    # Skip temperature selection for Bakes
    if ctype == "Bakes":
        varieties = MENU[ctype]['varieties']
        keyboard = []
        for variety_name, price in varieties.items():
            keyboard.append([InlineKeyboardButton(f"{variety_name} - ${price:.2f}", callback_data=f"var_{variety_name}")])
        
        await query.edit_message_text(
            f"You selected: {ctype}\n\nChoose your item:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return VARIETY
    
    # For drinks, show temperature options
    keyboard = [[InlineKeyboardButton(t, callback_data=f"temp_{t}")] for t in TEMPS]
    await query.edit_message_text(
        f"You selected: {ctype}\n\nChoose temperature:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TEMPERATURE

async def temp_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle temperature selection."""
    query = update.callback_query
    await query.answer()
    
    temp = query.data.replace("temp_", "")
    context.user_data['current']['temp'] = temp
    
    ctype = context.user_data['current']['type']
    varieties = MENU[ctype]['varieties']
    
    # Create buttons with prices
    keyboard = []
    for variety_name, price in varieties.items():
        keyboard.append([InlineKeyboardButton(f"{variety_name} - ${price:.2f}", callback_data=f"var_{variety_name}")])
    
    await query.edit_message_text(
        f"{ctype} - {temp}\n\nChoose your variety:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return VARIETY

async def variety_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle variety selection."""
    query = update.callback_query
    await query.answer()
    
    variety = query.data.replace("var_", "")
    context.user_data['current']['variety'] = variety
    
    # Get the base price for this specific variety
    ctype = context.user_data['current']['type']
    base_price = MENU[ctype]['varieties'][variety]
    context.user_data['current']['base_price'] = base_price
    
    # Skip add-ons for Bakes and go directly to cart
    if ctype == "Bakes":
        context.user_data['current']['temp'] = 'N/A'  # Set temp as N/A for bakes
        context.user_data['current']['price'] = base_price
        context.user_data['cart'].append(context.user_data['current'].copy())
        
        total = sum(item['price'] for item in context.user_data['cart'])
        summary = "📋 Your Cart:\n\n"
        for i, item in enumerate(context.user_data['cart'], 1):
            # Display differently for Bakes (no temperature)
            if item['type'] == 'Bakes':
                summary += f"{i}. {item['variety']}\n"
                summary += f"   ${item['price']:.2f}\n\n"
            else:
                addons_text = ", ".join(item['addons']) if item['addons'] else "None"
                summary += f"{i}. {item['variety']}\n"
                summary += f"   {item['temp']} {item['type']}\n"
                summary += f"   Add-ons: {addons_text}\n"
                summary += f"   ${item['price']:.2f}\n\n"
        summary += f"Total: ${total:.2f}"
        
        keyboard = [
            [InlineKeyboardButton("➕ Add Another Item", callback_data="add_more")],
            [InlineKeyboardButton("💳 Proceed to Checkout", callback_data="checkout")]
        ]
        
        await query.edit_message_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
        return REVIEW
    
    # For drinks, show add-ons
    keyboard = []
    for addon, price in ADDONS_MENU.items():
        price_text = f" (+${price:.2f})" if price > 0 else ""
        keyboard.append([InlineKeyboardButton(f"{addon}{price_text}", callback_data=f"addon_{addon}")])
    keyboard.append([InlineKeyboardButton("✅ Done with add-ons", callback_data="addon_done")])
    
    await query.edit_message_text(
        f"Great choice! {variety} (${base_price:.2f})\n\nSelect add-ons (tap multiple if needed):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADDONS

async def addon_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle addon selection."""
    query = update.callback_query
    
    if query.data == "addon_done":
        await query.answer()
        
        curr = context.user_data['current']
        base_price = curr['base_price']  # Use the stored base price for this variety
        addon_price = sum(ADDONS_MENU[a] for a in curr['addons'])
        curr['price'] = base_price + addon_price
        
        context.user_data['cart'].append(curr.copy())
        
        total = sum(item['price'] for item in context.user_data['cart'])
        summary = "📋 Your Cart:\n\n"
        for i, item in enumerate(context.user_data['cart'], 1):
            addons_text = ", ".join(item['addons']) if item['addons'] else "None"
            summary += f"{i}. {item['variety']}\n"
            summary += f"   {item['temp']} {item['type']}\n"
            summary += f"   Add-ons: {addons_text}\n"
            summary += f"   ${item['price']:.2f}\n\n"
        summary += f"Total: ${total:.2f}"
        
        keyboard = [
            [InlineKeyboardButton("➕ Add Another Item", callback_data="add_more")],
            [InlineKeyboardButton("💳 Proceed to Checkout", callback_data="checkout")]
        ]
        
        await query.edit_message_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
        return REVIEW
    else:
        addon = query.data.replace("addon_", "")
        if addon not in context.user_data['current']['addons']:
            context.user_data['current']['addons'].append(addon)
            await query.answer(f"✅ {addon} added!")
        else:
            await query.answer("Already added!")
        return ADDONS

async def review_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle add more or checkout."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_more":
        keyboard = [[InlineKeyboardButton(t, callback_data=f"type_{t}")] for t in MENU.keys()]
        await query.edit_message_text(
            "Select your coffee type:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return COFFEE_TYPE
    else:
        # Generate order ID using username
        username = query.from_user.username or query.from_user.first_name or "Customer"
        order_number = random.randint(100, 999)
        order_id = f"{username}_{order_number}"
        context.user_data['order_id'] = order_id
        
        total = sum(item['price'] for item in context.user_data['cart'])
        
        await query.edit_message_text(
            f"Order ID: #{order_id}\n"
            f"Total Amount: ${total:.2f}\n\n"
            "Please make payment via PayNow and send:\n"
            "• Screenshot of payment, OR\n"
            "• Type 'PAID' to confirm\n\n"
            "QR code will be sent in next message..."
        )
        
        try:
            with open('assets/paynow_qr.pdf', 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=photo,
                    caption=f"💳 Scan to pay ${total:.2f}\nOrder #{order_id}"
                )
        except FileNotFoundError:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"⚠️ QR code image not found. Please add 'paynow_qr.pdf' to the 'assets' folder.\n\nAmount to pay: ${total:.2f}"
            )
        
        return PAYMENT

async def payment_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle payment confirmation."""
    has_text = update.message.text and "PAID" in update.message.text.upper()
    has_photo = update.message.photo
    
    if has_text or has_photo:
        order_id = context.user_data.get('order_id', 'N/A')
        customer_name = update.effective_user.first_name or "Customer"
        customer_username = update.effective_user.username or "N/A"
        customer_id = update.effective_user.id
        
        save_order_to_file(order_id, customer_name, customer_username, customer_id, context.user_data['cart'])
        await notify_barista(context, order_id, customer_name, customer_username, context.user_data['cart'])
        
        await update.message.reply_text(
            f"✅ Payment received!\n\n"
            f"Order ID: #{order_id}\n"
            f"Your order is being prepared.\n\n"
            f"Thank you for ordering from Home Cafe! ☕\n\n"
            f"Type /start to place a new order."
        )
        
        context.user_data.clear()
        return ConversationHandler.END
    else:
        await update.message.reply_text("Please send a payment screenshot or type 'PAID' to confirm.")
        return PAYMENT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the order."""
    await update.message.reply_text("❌ Order cancelled.\n\nType /start to begin a new order.")
    context.user_data.clear()
    return ConversationHandler.END

def save_order_to_file(order_id, customer_name, customer_username, customer_id, cart):
    """Save order to CSV file."""
    import csv
    from datetime import datetime
    
    os.makedirs('orders', exist_ok=True)
    
    total = sum(item['price'] for item in cart)
    items_text = "; ".join([
        f"{item['variety']} ({item['temp']}) - Add-ons: {', '.join(item['addons']) if item['addons'] else 'None'}"
        for item in cart
    ])
    
    with open('orders/orders.csv', 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        if f.tell() == 0:
            writer.writerow(['Order ID', 'Date', 'Time', 'Customer Name', 'Username', 'User ID', 'Items', 'Total', 'Status'])
        
        now = datetime.now()
        writer.writerow([
            order_id,
            now.strftime('%Y-%m-%d'),
            now.strftime('%H:%M:%S'),
            customer_name,
            f"@{customer_username}" if customer_username != "N/A" else "N/A",
            customer_id,
            items_text,
            f"${total:.2f}",
            'pending'
        ])

async def notify_barista(context, order_id, customer_name, customer_username, cart):
    """Send order notification to barista."""
    BARISTA_CHAT_ID = "YOUR_TELEGRAM_USER_ID"
    
    if BARISTA_CHAT_ID == "YOUR_TELEGRAM_USER_ID":
        return
    
    total = sum(item['price'] for item in cart)
    order_text = f"🔔 *NEW ORDER #{order_id}*\n\n"
    order_text += f"👤 Customer: {customer_name}"
    if customer_username != "N/A":
        order_text += f" (@{customer_username})"
    order_text += "\n\n📋 *Order Details:*\n"
    
    for i, item in enumerate(cart, 1):
        addons_text = ", ".join(item['addons']) if item['addons'] else "None"
        order_text += f"{i}. {item['variety']}\n"
        order_text += f"   {item['temp']} {item['type']}\n"
        order_text += f"   Add-ons: {addons_text}\n"
        order_text += f"   ${item['price']:.2f}\n\n"
    
    order_text += f"💰 *Total: ${total:.2f}*"
    
    try:
        await context.bot.send_message(chat_id=BARISTA_CHAT_ID, text=order_text, parse_mode='Markdown')
    except Exception as e:
        print(f"Failed to send notification to barista: {e}")

async def view_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View recent orders."""
    import csv
    
    if not os.path.exists('orders/orders.csv'):
        await update.message.reply_text("No orders yet!")
        return
    
    with open('orders/orders.csv', 'r', encoding='utf-8') as f:
        reader = list(csv.reader(f))
        
        if len(reader) <= 1:
            await update.message.reply_text("No orders yet!")
            return
        
        orders = reader[-10:]
        
        message = "📋 *Recent Orders:*\n\n"
        for order in reversed(orders[1:]):
            order_id, date, time, customer, username, user_id, items, total = order[:8]
            status = order[8] if len(order) > 8 else 'pending'
            status_emoji = "✅" if status == "ready" else "⏳"
            message += f"{status_emoji} *{order_id}* - {date} {time}\n"
            message += f"Customer: {customer} {username}\n"
            message += f"Total: {total}\n\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')

async def today_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View today's orders and sales."""
    import csv
    from datetime import datetime
    
    if not os.path.exists('orders/orders.csv'):
        await update.message.reply_text("No orders yet!")
        return
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    with open('orders/orders.csv', 'r', encoding='utf-8') as f:
        reader = list(csv.reader(f))
        
        if len(reader) <= 1:
            await update.message.reply_text("No orders yet!")
            return
        
        today_orders_list = [row for row in reader[1:] if row[1] == today]
        
        if not today_orders_list:
            await update.message.reply_text("No orders today yet!")
            return
        
        total_sales = sum(float(order[7].replace('$', '')) for order in today_orders_list)
        
        message = f"📊 *Today's Summary ({today})*\n\n"
        message += f"Orders: {len(today_orders_list)}\n"
        message += f"Total Sales: ${total_sales:.2f}\n\n"
        message += "*Orders:*\n"
        
        for order in today_orders_list:
            order_id = order[0]
            customer = order[3]
            total = order[7]
            status = order[8] if len(order) > 8 else 'pending'
            status_emoji = "✅" if status == "ready" else "⏳"
            message += f"{status_emoji} {order_id} - {customer} - {total}\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')

async def view_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View pending orders."""
    import csv
    
    if not os.path.exists('orders/orders.csv'):
        await update.message.reply_text("No orders yet!")
        return
    
    with open('orders/orders.csv', 'r', encoding='utf-8') as f:
        reader = list(csv.reader(f))
        
        if len(reader) <= 1:
            await update.message.reply_text("No orders yet!")
            return
        
        pending = [row for row in reader[1:] if len(row) > 8 and row[8] == 'pending']
        
        if not pending:
            await update.message.reply_text("✅ No pending orders! All caught up!")
            return
        
        message = "⏳ *Pending Orders:*\n\n"
        for order in pending:
            order_id, date, time, customer, username, user_id, items, total, status = order
            message += f"*{order_id}*\n"
            message += f"Customer: {customer} {username}\n"
            message += f"Time: {time}\n"
            message += f"Items: {items}\n"
            message += f"Total: {total}\n\n"
        
        message += "Use /ready ORDER123 to mark as ready"
        
        await update.message.reply_text(message, parse_mode='Markdown')

async def mark_ready(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mark an order as ready and notify customer."""
    import csv
    
    if not context.args:
        await update.message.reply_text("Please specify order ID.\nUsage: /ready ORD12345")
        return
    
    order_id = context.args[0].upper()
    
    if not os.path.exists('orders/orders.csv'):
        await update.message.reply_text("No orders found!")
        return
    
    with open('orders/orders.csv', 'r', encoding='utf-8') as f:
        reader = list(csv.reader(f))
    
    order_found = False
    customer_chat_id = None
    customer_name = None
    
    for i, row in enumerate(reader):
        if i == 0:
            continue
        
        if row[0] == order_id and row[8] == 'pending':
            reader[i][8] = 'ready'
            customer_chat_id = row[5]
            customer_name = row[3]
            order_found = True
            break
    
    if not order_found:
        await update.message.reply_text(f"❌ Order {order_id} not found or already marked as ready.")
        return
    
    with open('orders/orders.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(reader)
    
    try:
        await context.bot.send_message(
            chat_id=customer_chat_id,
            text=f"☕ Good news, {customer_name}!\n\n"
                 f"Your order #{order_id} is ready for collection! 🎉\n\n"
                 f"Please come pick it up. Thank you!"
        )
        await update.message.reply_text(
            f"✅ Order {order_id} marked as ready!\n"
            f"Customer {customer_name} has been notified."
        )
    except Exception as e:
        await update.message.reply_text(
            f"✅ Order {order_id} marked as ready!\n"
            f"⚠️ Could not notify customer: {e}"
        )

def main() -> None:
    """Start the bot."""
    load_dotenv()
    
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    print(f"DEBUG: Token = '{BOT_TOKEN}'")
    
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN not found in .env file!")
        print("Please check your .env file and make sure it contains:")
        print("BOT_TOKEN=your_token_here (no spaces, no quotes)")
        return
    
    print(f"✅ Token loaded successfully!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            COFFEE_TYPE: [CallbackQueryHandler(coffee_selected, pattern="^type_")],
            TEMPERATURE: [CallbackQueryHandler(temp_selected, pattern="^temp_")],
            VARIETY: [CallbackQueryHandler(variety_selected, pattern="^var_")],
            ADDONS: [CallbackQueryHandler(addon_selected, pattern="^addon_")],
            REVIEW: [CallbackQueryHandler(review_action, pattern="^(add_more|checkout)$")],
            PAYMENT: [MessageHandler(filters.TEXT | filters.PHOTO, payment_done)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("orders", view_orders))
    app.add_handler(CommandHandler("today", today_orders))
    app.add_handler(CommandHandler("pending", view_pending))
    app.add_handler(CommandHandler("ready", mark_ready))
    
    print("🤖 Bot is running... Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()