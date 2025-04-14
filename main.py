



import os
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
)

TOKEN = "7355667192:AAG71GZ5n_yK64KGIXEmFfeArzQ3rDfStbU"
ADMIN_CHAT_ID = "1645299005"  # To receive orders
DB_URL = "postgresql://neondb_owner:npg_gulrS8dX3bio@ep-bold-boat-a4renqc3-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

# Cache for user carts and registration
user_carts = {}
user_states = {}

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cur.execute("SELECT * FROM users WHERE telegram_id = %s", (user_id,))
    user = cur.fetchone()

    if not user:
        user_states[user_id] = "awaiting_name"
        await update.message.reply_text("👋 مرحبًا! أدخل اسمك الكامل:")
        return

    keyboard = [
        [InlineKeyboardButton("تصفح المنتجات 🛍️", callback_data="browse")],
        [InlineKeyboardButton("طلباتي 🛒", callback_data="my_orders")]
    ]
    await update.message.reply_text("مرحبًا بك مجددًا! ✨", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id in user_states:
        state = user_states[user_id]

        if state == "awaiting_name":
            context.user_data["name"] = text
            user_states[user_id] = "awaiting_address"
            await update.message.reply_text("📍 أدخل عنوانك:")
        elif state == "awaiting_address":
            context.user_data["address"] = text
            user_states[user_id] = "awaiting_wilaya"
            await update.message.reply_text("🌍 أدخل الولاية:")
        elif state == "awaiting_wilaya":
            context.user_data["wilaya"] = text
            user_states[user_id] = "awaiting_town"
            await update.message.reply_text("🏘️ أدخل المدينة:")
        elif state == "awaiting_town":
            context.user_data["town"] = text
            user_states[user_id] = "awaiting_phone"
            await update.message.reply_text("📞 أدخل رقم هاتفك:")
        elif state == "awaiting_phone":
            context.user_data["phone"] = text

            cur.execute("""
                INSERT INTO users (telegram_id, name, address, wilaya, town, phone)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                context.user_data["name"],
                context.user_data["address"],
                context.user_data["wilaya"],
                context.user_data["town"],
                context.user_data["phone"]
            ))
            conn.commit()

            del user_states[user_id]
            await update.message.reply_text("✅ تم التسجيل بنجاح!")
            await start(update, context)

async def browse_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    cur.execute("SELECT id, name, price FROM products")
    rows = cur.fetchall()

    keyboard = [
        [InlineKeyboardButton(f"{name} - {price} دج", callback_data=f"product_{pid}")]
        for pid, name, price in rows
    ]
    keyboard.append([InlineKeyboardButton("↩️ رجوع", callback_data="back_start")])

    await query.edit_message_text("🏷️ المنتجات المتاحة:", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pid = int(query.data.split("_")[1])

    cur.execute("SELECT name, price, description, photo_url FROM products WHERE id = %s", (pid,))
    name, price, desc, photo = cur.fetchone()

    keyboard = [
        [InlineKeyboardButton("🛒 أضف إلى السلة", callback_data=f"add_{pid}")],
        [InlineKeyboardButton("↩️ رجوع", callback_data="browse")]
    ]
    await context.bot.send_photo(
        chat_id=query.message.chat_id,
        photo=photo,
        caption=f"*{name}*\n\n💰 السعر: {price} دج\n\n{desc}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await query.delete_message()

async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    pid = int(query.data.split("_")[1])
    user_carts.setdefault(user_id, []).append(pid)
    await query.answer("✅ تمت الإضافة إلى السلة")

async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cart = user_carts.get(user_id, [])

    if not cart:
        await query.edit_message_text("🚫 السلة فارغة")
        return

    item_texts = []
    total = 0

    for pid in cart:
        cur.execute("SELECT name, price FROM products WHERE id = %s", (pid,))
        name, price = cur.fetchone()
        item_texts.append(f"- {name} ({price} دج)")
        total += price

    keyboard = [
        [InlineKeyboardButton("✅ تأكيد الطلب", callback_data="confirm_order")],
        [InlineKeyboardButton("🗑️ حذف السلة", callback_data="clear_cart")]
    ]
    await query.edit_message_text(
        f"🛒 السلة:\n\n" + "\n".join(item_texts) + f"\n\n💰 المجموع: {total} دج",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    cart = user_carts.get(user.id, [])

    if not cart:
        await query.answer("❌ لا توجد عناصر")
        return

    cur.execute("SELECT name FROM products WHERE id = ANY(%s)", (cart,))
    items = [row[0] for row in cur.fetchall()]
    cur.execute("SELECT * FROM users WHERE telegram_id = %s", (user.id,))
    user_info = cur.fetchone()

    cur.execute("""
        INSERT INTO orders (user_id, product_ids)
        VALUES (%s, %s)
    """, (user.id, cart))
    conn.commit()

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"📦 طلب جديد من {user_info[2]}\n\nالمنتجات:\n" + "\n".join(items)
    )
    user_carts[user.id] = []
    await query.edit_message_text("✅ تم إرسال طلبك! سنتواصل معك قريبًا.")

async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    user_carts[user_id] = []
    await update.callback_query.edit_message_text("🗑️ تم إفراغ السلة")

# --- Main ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(browse_products, pattern="^browse$"))
    app.add_handler(CallbackQueryHandler(show_product, pattern="^product_"))
    app.add_handler(CallbackQueryHandler(add_to_cart, pattern="^add_"))
    app.add_handler(CallbackQueryHandler(view_cart, pattern="^my_orders$"))
    app.add_handler(CallbackQueryHandler(confirm_order, pattern="^confirm_order$"))
    app.add_handler(CallbackQueryHandler(clear_cart, pattern="^clear_cart$"))
    app.add_handler(CallbackQueryHandler(start, pattern="^back_start$"))
    app.run_polling()

if __name__ == "__main__":
    main()

