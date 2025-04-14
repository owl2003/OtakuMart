import os
import asyncpg
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    ContextTypes, MessageHandler, filters
)

# Configuration (hardcoded as requested)
TOKEN = "7355667192:AAG71GZ5n_yK64KGIXEmFfeArzQ3rDfStbU"
ADMIN_CHAT_ID = 1645299005
DB_URL = "postgresql://neondb_owner:npg_gulrS8dX3bio@ep-bold-boat-a4renqc3-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database connection pool
db_pool = None

class UserState:
    AWAITING_NAME = 1
    AWAITING_ADDRESS = 2
    AWAITING_WILAYA = 3
    AWAITING_TOWN = 4
    AWAITING_PHONE = 5

async def init_db():
    """Initialize database connection pool"""
    return await asyncpg.create_pool(
        DB_URL,
        min_size=5,
        max_size=20,
        command_timeout=60
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    try:
        async with db_pool.acquire() as conn:
            user_exists = await conn.fetchval(
                "SELECT 1 FROM users WHERE telegram_id = $1", 
                user.id
            )
    except Exception as e:
        logger.error(f"Database error in start handler: {e}")
        await update.message.reply_text("❌ حدث خطأ في النظام. يرجى المحاولة لاحقاً.")
        return

    if not user_exists:
        context.user_data['state'] = UserState.AWAITING_NAME
        await update.message.reply_text("👋 مرحباً بك! الرجاء إدخال اسمك الكامل:")
    else:
        keyboard = [
            [InlineKeyboardButton("تصفح المنتجات 🛍️", callback_data="browse")],
            [InlineKeyboardButton("طلباتي 🛒", callback_data="my_orders")]
        ]
        await update.message.reply_text(
            "مرحباً بك مجدداً! ✨",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    user = update.effective_user
    text = update.message.text
    
    if 'state' not in context.user_data:
        await update.message.reply_text("الرجاء استخدام الأوامر من القائمة.")
        return

    state = context.user_data['state']

    if state == UserState.AWAITING_NAME:
        context.user_data['name'] = text
        context.user_data['state'] = UserState.AWAITING_ADDRESS
        await update.message.reply_text("📍 الرجاء إدخال عنوانك:")
    
    elif state == UserState.AWAITING_ADDRESS:
        context.user_data['address'] = text
        context.user_data['state'] = UserState.AWAITING_WILAYA
        await update.message.reply_text("🌍 الرجاء إدخال الولاية:")
    
    elif state == UserState.AWAITING_WILAYA:
        context.user_data['wilaya'] = text
        context.user_data['state'] = UserState.AWAITING_TOWN
        await update.message.reply_text("🏘️ الرجاء إدخال المدينة:")
    
    elif state == UserState.AWAITING_TOWN:
        context.user_data['town'] = text
        context.user_data['state'] = UserState.AWAITING_PHONE
        await update.message.reply_text("📞 الرجاء إدخال رقم الهاتف:")
    
    elif state == UserState.AWAITING_PHONE:
        context.user_data['phone'] = text
        
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO users 
                    (telegram_id, name, address, wilaya, town, phone)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    user.id,
                    context.user_data['name'],
                    context.user_data['address'],
                    context.user_data['wilaya'],
                    context.user_data['town'],
                    context.user_data['phone']
                )
        except Exception as e:
            logger.error(f"Error saving user: {e}")
            await update.message.reply_text("❌ حدث خطأ أثناء حفظ البيانات. يرجى المحاولة مرة أخرى.")
            return
        
        del context.user_data['state']
        await update.message.reply_text("✅ تم التسجيل بنجاح!")
        await start(update, context)

async def browse_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show product list"""
    query = update.callback_query
    await query.answer()

    try:
        async with db_pool.acquire() as conn:
            products = await conn.fetch("SELECT id, name, price FROM products")
    except Exception as e:
        logger.error(f"Error fetching products: {e}")
        await query.edit_message_text("❌ حدث خطأ في جلب المنتجات.")
        return

    if not products:
        await query.edit_message_text("⚠️ لا توجد منتجات متاحة حالياً.")
        return

    keyboard = [
        [InlineKeyboardButton(f"{p['name']} - {p['price']} دج", callback_data=f"product_{p['id']}")]
        for p in products
    ]
    keyboard.append([InlineKeyboardButton("↩️ رجوع", callback_data="back_start")])

    await query.edit_message_text(
        "🏷️ المنتجات المتاحة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show product details"""
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[1])

    try:
        async with db_pool.acquire() as conn:
            product = await conn.fetchrow(
                "SELECT name, price, description, photo_url FROM products WHERE id = $1",
                product_id
            )
    except Exception as e:
        logger.error(f"Error fetching product {product_id}: {e}")
        await query.edit_message_text("❌ حدث خطأ في جلب تفاصيل المنتج.")
        return

    if not product:
        await query.edit_message_text("⚠️ المنتج غير متوفر.")
        return

    keyboard = [
        [InlineKeyboardButton("🛒 أضف إلى السلة", callback_data=f"add_{product_id}")],
        [InlineKeyboardButton("↩️ رجوع", callback_data="browse")]
    ]

    try:
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=product['photo_url'],
            caption=f"*{product['name']}*\n\n💰 السعر: {product['price']} دج\n\n{product['description']}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await query.delete_message()
    except Exception as e:
        logger.error(f"Error sending product photo: {e}")
        await query.edit_message_text(
            f"*{product['name']}*\n\n💰 السعر: {product['price']} دج\n\n{product['description']}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add product to cart"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    product_id = int(query.data.split("_")[1])

    try:
        async with db_pool.acquire() as conn:
            # Check if product exists
            product_exists = await conn.fetchval(
                "SELECT 1 FROM products WHERE id = $1",
                product_id
            )
            if not product_exists:
                await query.answer("⚠️ المنتج غير متوفر")
                return

            # Add to cart
            await conn.execute(
                "INSERT INTO cart_items (user_id, product_id) VALUES ($1, $2)",
                user_id, product_id
            )
    except Exception as e:
        logger.error(f"Error adding to cart: {e}")
        await query.answer("❌ حدث خطأ أثناء إضافة المنتج للسلة")
        return

    await query.answer("✅ تمت الإضافة إلى السلة")

async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View user's cart"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    try:
        async with db_pool.acquire() as conn:
            cart_items = await conn.fetch(
                """
                SELECT p.id, p.name, p.price 
                FROM cart_items ci
                JOIN products p ON ci.product_id = p.id
                WHERE ci.user_id = $1
                """,
                user_id
            )
    except Exception as e:
        logger.error(f"Error fetching cart: {e}")
        await query.edit_message_text("❌ حدث خطأ في جلب محتويات السلة")
        return

    if not cart_items:
        await query.edit_message_text("🛒 سلة التسوق فارغة")
        return

    total = sum(item['price'] for item in cart_items)
    items_text = "\n".join(f"- {item['name']} ({item['price']} دج)" for item in cart_items)

    keyboard = [
        [InlineKeyboardButton("✅ تأكيد الطلب", callback_data="confirm_order")],
        [InlineKeyboardButton("🗑️ إفراغ السلة", callback_data="clear_cart")],
        [InlineKeyboardButton("↩️ رجوع", callback_data="back_start")]
    ]

    await query.edit_message_text(
        f"🛒 سلة التسوق:\n\n{items_text}\n\n💰 المجموع: {total} دج",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm order from cart"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    try:
        async with db_pool.acquire() as conn:
            # Get cart items
            cart_items = await conn.fetch(
                """
                SELECT p.id, p.name, p.price 
                FROM cart_items ci
                JOIN products p ON ci.product_id = p.id
                WHERE ci.user_id = $1
                """,
                user.id
            )

            if not cart_items:
                await query.answer("⚠️ السلة فارغة")
                return

            # Get user info
            user_info = await conn.fetchrow(
                "SELECT name, phone, address FROM users WHERE telegram_id = $1",
                user.id
            )

            # Create order
            product_ids = [item['id'] for item in cart_items]
            total = sum(item['price'] for item in cart_items)
            
            await conn.execute(
                """
                INSERT INTO orders (user_id, product_ids, total_amount, status)
                VALUES ($1, $2, $3, 'pending')
                """,
                user.id, product_ids, total
            )

            # Clear cart
            await conn.execute(
                "DELETE FROM cart_items WHERE user_id = $1",
                user.id
            )
    except Exception as e:
        logger.error(f"Error confirming order: {e}")
        await query.edit_message_text("❌ حدث خطأ أثناء تأكيد الطلب")
        return

    # Prepare order summary for admin
    items_text = "\n".join(f"- {item['name']} ({item['price']} دج)" for item in cart_items)
    order_text = (
        f"📦 طلب جديد\n\n"
        f"👤 العميل: {user_info['name']}\n"
        f"📞 الهاتف: {user_info['phone']}\n"
        f"📍 العنوان: {user_info['address']}\n\n"
        f"🛒 المنتجات:\n{items_text}\n\n"
        f"💰 المجموع: {total} دج"
    )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=order_text
        )
    except Exception as e:
        logger.error(f"Error sending order to admin: {e}")

    await query.edit_message_text(
        "✅ تم تأكيد طلبك بنجاح! سنتصل بك قريباً لتأكيد التفاصيل."
    )

async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear user's cart"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM cart_items WHERE user_id = $1",
                user_id
            )
    except Exception as e:
        logger.error(f"Error clearing cart: {e}")
        await query.answer("❌ حدث خطأ أثناء إفراغ السلة")
        return

    await query.edit_message_text("🗑️ تم إفراغ السلة بنجاح")

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to start menu"""
    query = update.callback_query
    await query.answer()
    await start(update, context)

async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to view orders"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ غير مصرح لك بهذا الأمر")
        return

    try:
        async with db_pool.acquire() as conn:
            orders = await conn.fetch(
                """
                SELECT o.id, o.created_at, o.total_amount, o.status,
                       u.name as user_name, u.phone,
                       array_agg(p.name) as product_names
                FROM orders o
                JOIN users u ON o.user_id = u.telegram_id
                JOIN unnest(o.product_ids) WITH ORDINALITY AS product(id, ord)
                JOIN products p ON product.id = p.id
                GROUP BY o.id, u.name, u.phone
                ORDER BY o.created_at DESC
                LIMIT 10
                """
            )
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        await update.message.reply_text("❌ حدث خطأ في جلب الطلبات")
        return

    if not orders:
        await update.message.reply_text("📭 لا توجد طلبات حالياً")
        return

    orders_text = []
    for order in orders:
        order_text = (
            f"🆔 رقم الطلب: {order['id']}\n"
            f"📅 التاريخ: {order['created_at'].strftime('%Y-%m-%d %H:%M')}\n"
            f"👤 العميل: {order['user_name']}\n"
            f"📞 الهاتف: {order['phone']}\n"
            f"🛒 المنتجات:\n- " + "\n- ".join(order['product_names']) + "\n"
            f"💰 المبلغ: {order['total_amount']} دج\n"
            f"📊 الحالة: {order['status']}\n"
        )
        orders_text.append(order_text)

    await update.message.reply_text(
        "📋 آخر 10 طلبات:\n\n" + "\n\n".join(orders_text)
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")
    if update and hasattr(update, 'message'):
        await update.message.reply_text("❌ حدث خطأ غير متوقع. يرجى المحاولة لاحقاً.")

async def main():
    """Start the bot"""
    global db_pool
    db_pool = await init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin_orders", admin_orders))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Callback handlers
    app.add_handler(CallbackQueryHandler(browse_products, pattern="^browse$"))
    app.add_handler(CallbackQueryHandler(show_product, pattern="^product_"))
    app.add_handler(CallbackQueryHandler(add_to_cart, pattern="^add_"))
    app.add_handler(CallbackQueryHandler(view_cart, pattern="^my_orders$"))
    app.add_handler(CallbackQueryHandler(confirm_order, pattern="^confirm_order$"))
    app.add_handler(CallbackQueryHandler(clear_cart, pattern="^clear_cart$"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_start$"))
    
    # Error handler
    app.add_error_handler(error_handler)

    # Start polling
    await app.run_polling()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
