import os
import asyncpg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
)

TOKEN = "7355667192:AAG71GZ5n_yK64KGIXEmFfeArzQ3rDfStbU"
ADMIN_CHAT_ID = "1645299005"  # To receive orders
DB_URL = "postgresql://neondb_owner:npg_gulrS8dX3bio@ep-bold-boat-a4renqc3-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

# Initialize connection pool
async def init_db():
    return await asyncpg.create_pool(DB_URL)

# Global variable for the database connection pool
db_pool = None

# Cache for user carts and registration
user_carts = {}
user_states = {}

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", user_id)
    except Exception as e:
        await update.message.reply_text("❌ Error while accessing the database.")
        print(f"Database error in start handler: {e}")
        return

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

            try:
                async with db_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO users (telegram_id, name, address, wilaya, town, phone)
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """, user_id, context.user_data["name"], context.user_data["address"],
                        context.user_data["wilaya"], context.user_data["town"], context.user_data["phone"])
            except Exception as e:
                await update.message.reply_text("❌ Error while saving user data.")
                print(f"Error in saving user data: {e}")
                return

            del user_states[user_id]
            await update.message.reply_text("✅ تم التسجيل بنجاح!")
            await start(update, context)

async def browse_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, name, price FROM products")
    except Exception as e:
        await query.edit_message_text("❌ Error while fetching products.")
        print(f"Error fetching products: {e}")
        return

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

    try:
        async with db_pool.acquire() as conn:
            product = await conn.fetchrow("SELECT name, price, description, photo_url FROM products WHERE id = $1", pid)
    except Exception as e:
        await query.edit_message_text("❌ Error while fetching product details.")
        print(f"Error fetching product details: {e}")
        return

    name, price, desc, photo = product

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

    try:
        async with db_pool.acquire() as conn:
            await conn.execute("INSERT INTO carts (user_id, product_id) VALUES ($1, $2)", user_id, pid)
    except Exception as e:
        await query.answer("❌ Error while adding to cart.")
        print(f"Error adding to cart: {e}")
        return

    await query.answer("✅ تمت الإضافة إلى السلة")

async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    try:
        async with db_pool.acquire() as conn:
            cart = await conn.fetch("SELECT product_id FROM carts WHERE user_id = $1", user_id)
    except Exception as e:
        await query.edit_message_text("❌ Error while fetching the cart.")
        print(f"Error fetching cart: {e}")
        return

    if not cart:
        await query.edit_message_text("🚫 السلة فارغة")
        return

    item_texts = []
    total = 0

    for pid in cart:
        async with db_pool.acquire() as conn:
            product = await conn.fetchrow("SELECT name, price FROM products WHERE id = $1", pid[0])
        name, price = product
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

    try:
        async with db_pool.acquire() as conn:
            items = []
            for pid in cart:
                product = await conn.fetchrow("SELECT name FROM products WHERE id = $1", pid)
                items.append(product['name'])
            user_info = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", user.id)

            await conn.execute("""
                INSERT INTO orders (user_id, product_ids)
                VALUES ($1, $2)
            """, user.id, cart)
    except Exception as e:
        await query.answer("❌ Error while confirming order.")
        print(f"Error confirming order: {e}")
        return

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"📦 طلب جديد من {user_info['name']}\n\nالمنتجات:\n" + "\n".join(items)
    )
    user_carts[user.id] = []
    await query.edit_message_text("✅ تم إرسال طلبك! سنتواصل معك قريبًا.")

async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    user_carts[user_id] = []
    await update.callback_query.edit_message_text("🗑️ تم إفراغ السلة")

# --- Admin Command ---
async def manage_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_CHAT_ID:
        return

    # Fetch all orders
    try:
        async with db_pool.acquire() as conn:
            orders = await conn.fetch("SELECT id, user_id, product_ids FROM orders")
    except Exception as e:
        await update.message.reply_text("❌ Error while fetching orders.")
        print(f"Error fetching orders: {e}")
        return

    if not orders:
        await update.message.reply_text("🚫 لا توجد طلبات جديدة.")
        return

    order_texts = []
    for order in orders:
        user_id, product_ids = order['user_id'], order['product_ids']
        user_name = await conn.fetchval("SELECT name FROM users WHERE telegram_id = $1", user_id)
        product_names = []
        for pid in product_ids:
            product_name = await conn.fetchval("SELECT name FROM products WHERE id = $1", pid)
            product_names.append(product_name)
        order_texts.append(f"طلب من {user_name}:\n" + "\n".join(product_names))

    await update.message.reply_text("\n\n".join(order_texts))

# --- Main ---
async def main():
    global db_pool
    db_pool = await init_db()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(browse_products, pattern="^browse$"))
    app.add_handler(CallbackQueryHandler(show_product, pattern="^product_"))
    app.add_handler(CallbackQueryHandler(add_to_cart, pattern="^add_"))
    app.add_handler(CallbackQueryHandler(view_cart, pattern="^my_orders$"))
    app.add_handler(CallbackQueryHandler(confirm_order, pattern="^confirm_order$"))
    app.add_handler(CallbackQueryHandler(clear_cart, pattern="^clear_cart$"))
    app.add_handler(CommandHandler("admin_orders", manage_orders))

    await app.run_polling()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
