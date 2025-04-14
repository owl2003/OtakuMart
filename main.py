import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# Configuration
TOKEN = "7355667192:AAG71GZ5n_yK64KGIXEmFfeArzQ3rDfStbU"
ADMIN_CHAT_ID = "1645299005"  # To receive orders

# Sample Arabic product database
products = {
    "fig1": {
        "name": "تمثال ناروتو",
        "price": 3000,
        "desc": "حجم 15 سم، إصدار محدود",
        "photo": "https://i.imgur.com/JqYeYn7.jpg"
    },
    "poster1": {
        "name": "ملصق ديمون سلاير",
        "price": 500,
        "desc": "مقاس A3، طبعة عالية الجودة",
        "photo": "https://i.imgur.com/p6Qb6Qq.jpg"
    }
}

# Order storage (in production, use a database)
user_carts = {}

# ----- Bot Handlers -----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("تصفح المنتجات 🛍️", callback_data="browse")],
        [InlineKeyboardButton("طلباتي 🛒", callback_data="my_orders")]
    ]
    await update.message.reply_text(
        "مرحبًا بك في متجر الأنمي الجزائري! 🇩🇿\n\n"
        "الدفع عند الاستلام في جميع الولايات",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def browse_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(
            f"{item['name']} - {item['price']} دج",
            callback_data=f"product_{product_id}"
        )] for product_id, item in products.items()
    ]
    keyboard.append([InlineKeyboardButton("العودة ↩️", callback_data="back_start")])
    await query.edit_message_text(
        "🏷️ قائمة المنتجات:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = query.data.split("_")[1]
    product = products[product_id]

    keyboard = [
        [InlineKeyboardButton("أضف إلى السلة 🛒", callback_data=f"add_{product_id}")],
        [InlineKeyboardButton("عودة ↩️", callback_data="browse")]
    ]

    await context.bot.send_photo(
        chat_id=query.message.chat_id,
        photo=product["photo"],
        caption=f"*{product['name']}*\n\nالسعر: {product['price']} دج\n\n{product['desc']}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    await query.delete_message()

async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    product_id = query.data.split("_")[1]

    user_carts.setdefault(user_id, []).append(product_id)
    await query.answer(f"✅ تمت إضافة {products[product_id]['name']} إلى السلة")

async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in user_carts or not user_carts[user_id]:
        await query.edit_message_text("سلة التسوق فارغة!")
        return

    items = []
    total = 0
    for product_id in user_carts[user_id]:
        item = products[product_id]
        items.append(f"・ {item['name']} ({item['price']} دج)")
        total += item["price"]

    keyboard = [
        [InlineKeyboardButton("تأكيد الطلب ✅", callback_data="confirm_order")],
        [InlineKeyboardButton("حذف السلة 🗑️", callback_data="clear_cart")]
    ]

    await query.edit_message_text(
        f"🛒 سلة التسوق:\n\n" + "\n".join(items) + f"\n\nالمجموع: {total} دج",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if user.id not in user_carts or not user_carts[user.id]:
        await query.answer("السلة فارغة!")
        return

    order_items = []
    total = 0
    for product_id in user_carts[user.id]:
        item = products[product_id]
        order_items.append(f"- {item['name']} ({item['price']} دج)")
        total += item["price"]

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"🎌 طلب جديد!\n\n"
             f"الزبون: {user.full_name} (@{user.username})\n"
             f"الطلبات:\n" + "\n".join(order_items) + f"\n\n"
             f"المجموع: {total} دج\n\n"
             f"رقم التواصل: {user.id}"
    )

    await query.edit_message_text(
        "شكرًا لطلبك! 🎉\n\n"
        "سيتم التواصل معك خلال 24 ساعة لتأكيد العنوان.\n"
        "الدفع نقدًا عند الاستلام."
    )

    user_carts.pop(user.id)

# ----- Main Setup -----
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(browse_products, pattern="^browse$"))
    app.add_handler(CallbackQueryHandler(view_cart, pattern="^my_orders$"))
    app.add_handler(CallbackQueryHandler(show_product, pattern="^product_"))
    app.add_handler(CallbackQueryHandler(add_to_cart, pattern="^add_"))
    app.add_handler(CallbackQueryHandler(confirm_order, pattern="^confirm_order$"))

    app.run_polling()

if __name__ == "__main__":
    main()
