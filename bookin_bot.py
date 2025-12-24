from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = "7875676177:AAGcZvpYSxnjqBaMBbUN61JwEuthpZuARMk"
ADMIN_ID = 850788066  # <-- ID администратора

ASK_NAME, ASK_PHONE = range(2)
user_states = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Добро пожаловать в *FoxEnglish!*\n\n"
        "В связи с праздниками ближайшее бесплатное онлайн занятие состоится *9 января*.\n\n"
        "Хотите записаться на 9 января?"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Записаться на 9 января", callback_data="signup")],
        [InlineKeyboardButton("🔔 Уведомить о следующих занятиях", callback_data="notify")]
    ])

    await update.message.reply_text(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data in ("signup", "notify"):
        user_states[query.from_user.id] = ASK_NAME
        await query.message.reply_text("Как вас зовут?")

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_states.get(user_id) == ASK_NAME:
        context.user_data["name"] = update.message.text
        user_states[user_id] = ASK_PHONE

        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Отправить номер телефона", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )

        await update.message.reply_text(
            "Спасибо! Теперь отправьте, пожалуйста, ваш номер телефона.",
            reply_markup=keyboard
        )

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_states.get(user_id) == ASK_PHONE:
        phone = update.message.contact.phone_number
        name = context.user_data.get("name")
        username = update.message.from_user.username

        user_states.pop(user_id, None)

        # Сообщение админу
        admin_text = (
            "📥 *Новая заявка FoxEnglish*\n\n"
            f"👤 Имя: {name}\n"
            f"📱 Телефон: {phone}\n"
            f"🔗 Username: @{username if username else 'нет'}\n"
            f"🆔 User ID: {user_id}"
        )

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            parse_mode="Markdown"
        )

        await update.message.reply_text(
            f"✅ Спасибо, *{name}*!\n\n"
            "Вы успешно записаны. Мы свяжемся с вами перед занятием 📞",
            parse_mode="Markdown"
        )

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name))
    app.add_handler(MessageHandler(filters.CONTACT, handle_phone))

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()