from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
import os

TOKEN = os.getenv("7355667192:AAG71GZ5n_yK64KGIXEmFfeArzQ3rDfStbU")  # اضبطه في البيئة (لا تضعه في الكود مباشرة!)

# قاعدة بيانات المنتجات (بالعربية)
products = {
    "fig1": {
        "name": "تمثال ناروتو",
        "price": 3000,  # دينار جزائري
        "desc": "حجم 15 سم، إصدار محدود",
        "photo": "https://example.com/naruto.jpg"
    },
    "poster1": {
        "name": "ملصق ديمون سلاير",
        "price": 500,
        "desc": "مقاس A3، طبعة عالية الجودة",
        "photo": "https://example.com/ds_poster.jpg"
    }
}

# طلبات الزبائن (في الذاكرة، استخدم قاعدة بيانات للإنتاج)
orders = {}


def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("تصفح المنتجات 🛍️", callback_data="browse")],
        [InlineKeyboardButton("طلباتي 🛒", callback_data="my_orders")]
    ]
    update.message.reply_text(
        "مرحبًا بك في *متجر الأنمي الجزائري*! 🇩🇿\n\n"
        "يمكنك الطلب والدفع عند الاستلام.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


def browse_products(update: Update, context: CallbackContext):
    query = update.callback_query
    keyboard = []
    for product_id, item in products.items():
        keyboard.append([InlineKeyboardButton(
            f"{item['name']} - {item['price']} دج",
            callback_data=f"product_{product_id}"
        )])
    keyboard.append([InlineKeyboardButton("العودة ↩️", callback_data="back_start")])
    query.edit_message_text(
        "🏷️ *قائمة المنتجات*:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


def product_detail(update: Update, context: CallbackContext):
    query = update.callback_query
    product_id = query.data.split("_")[1]
    product = products[product_id]

    keyboard = [
        [InlineKeyboardButton("أضف إلى السلة 🛒", callback_data=f"order_{product_id}")],
        [InlineKeyboardButton("عودة ↩️", callback_data="browse")]
    ]

    context.bot.send_photo(
        chat_id=query.message.chat_id,
        photo=product["photo"],
        caption=f"*{product['name']}*\n\nالسعر: {product['price']} دج\n\n{product['desc']}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    query.delete_message()


def place_order(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    product_id = query.data.split("_")[1]

    if user_id not in orders:
        orders[user_id] = []
    orders[user_id].append(products[product_id])

    # إرسال تفاصيل الطلب للمستخدم
    order_summary = f"✅ تمت إضافة *{products[product_id]['name']}* إلى طلباتك!\n\n"
    order_summary += "سيتم التواصل معك لتأكيد العنوان والدفع عند الاستلام."

    query.answer()
    context.bot.send_message(
        chat_id=query.message.chat_id,
        text=order_summary,
        parse_mode="Markdown"
    )


def my_orders(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in orders or not orders[user_id]:
        query.edit_message_text("لا توجد طلبات حالية!")
        return

    order_list = "📋 *طلباتك الحالية*:\n\n"
    total = 0
    for item in orders[user_id]:
        order_list += f"・ {item['name']} - {item['price']} دج\n"
        total += item["price"]

    order_list += f"\nالمجموع: {total} دج\n\n"
    order_list += "سيتم التواصل معك قريبًا للتوصيل."

    keyboard = [[InlineKeyboardButton("إغلاق ❌", callback_data="close_orders")]]
    query.edit_message_text(
        order_list,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    # الأوامر
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(browse_products, pattern="^browse$"))
    dp.add_handler(CallbackQueryHandler(my_orders, pattern="^my_orders$"))
    dp.add_handler(CallbackQueryHandler(product_detail, pattern="^product_"))
    dp.add_handler(CallbackQueryHandler(place_order, pattern="^order_"))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
