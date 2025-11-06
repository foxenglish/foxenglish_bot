# bot.py
import os
import logging
from datetime import datetime, timedelta, date
import asyncio

import aiosqlite
from dotenv import load_dotenv

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# --- Загрузка переменных из .env ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "bookings.db")
CAPACITY = int(os.getenv("CAPACITY", "10"))

# --- Состояния ConversationHandler ---
CHOOSING_CLASS, CHOOSING_DATE, CHOOSING_TIME, ENTER_NAME, ENTER_PHONE = range(5)

# --- Настройки: названия классов и слоты ---
AVAILABLE_CLASSES = ["Вторник", "Воскресенье"]
TIME_SLOTS = ["12:00 по Москве", "16:00 по Москве"]

# --- Инициализация базы данных ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                name TEXT,
                phone TEXT,
                class_name TEXT,
                date TEXT,
                time TEXT,
                created_at TEXT,
                reminded_24h INTEGER DEFAULT 0,
                reminded_3h INTEGER DEFAULT 0
            )
            """
        )
        await db.commit()

# --- Очистка старых записей ---
async def cleanup_old_bookings():
    """Удаляет записи, где дата занятия уже прошла."""
    today = date.today()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM bookings WHERE date < ?", (today.isoformat(),))
        await db.commit()
    print("🧹 Старые записи успешно удалены")

async def send_reminders(app):
    """Фоновая задача — отправляет напоминания за 24 часа и за 3 часа."""
    while True:
        now = datetime.utcnow()
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT id, user_id, class_name, date, time, reminded_24h, reminded_3h FROM bookings"
            )
            rows = await cur.fetchall()

            for r in rows:
                booking_id, user_id, class_name, date_str, time_str, reminded_24h, reminded_3h = r
                try:
                    # Формируем datetime занятия в UTC (Москва = UTC+3)
                    local_time = datetime.strptime(f"{date_str} {time_str[:5]}", "%Y-%m-%d %H:%M")
                    class_time_utc = local_time - timedelta(hours=3)

                    hours_left = (class_time_utc - now).total_seconds() / 3600

                    # Напоминание за 24 часа
                    if 23 <= hours_left <= 24 and not reminded_24h:
                        text = (
                            f"⏰ Напоминание!\n"
                            f"Вы записаны на онлайн занятие FoxEnglish {class_name} {date_str} в {time_str} (по Москве).\n"
                            f"До начала осталось примерно 24 часа! Мы вам пришлём ссылку на заниятие за 15 минут"
                        )
                        await app.bot.send_message(chat_id=user_id, text=text)
                        await db.execute("UPDATE bookings SET reminded_24h=1 WHERE id=?", (booking_id,))
                        await db.commit()

                    # Напоминание за 3 часа
                    elif 2.5 <= hours_left <= 3.5 and not reminded_3h:
                        text = (
                            f"📢 Напоминание!\n"
                            f"Ваше онлайн занятие FoxEnglish {class_name} начнётся через 3 часа! Мы вам пришлём ссылку на заниятие за 15 минут\n"
                            f"Дата: {date_str}, время: {time_str} (по Москве)."
                        )
                        await app.bot.send_message(chat_id=user_id, text=text)
                        await db.execute("UPDATE bookings SET reminded_3h=1 WHERE id=?", (booking_id,))
                        await db.commit()

                except Exception as e:
                    print(f"⚠️ Ошибка при обработке напоминания для {booking_id}: {e}")

        await asyncio.sleep(900)  # проверять каждые 15 минут


# --- Вспомогательные клавиатуры ---
def build_classes_keyboard():
    rows = [[
        InlineKeyboardButton("Вторник", callback_data="class_Вторник"),
        InlineKeyboardButton("Воскресенье", callback_data="class_Воскресенье")
    ]]
    return InlineKeyboardMarkup(rows)

def build_dates_keyboard(class_name, days=14):
    """Показываем только ближайшие вторники или воскресенья."""
    start = datetime.now().date()
    rows = []
    day_index = 1 if class_name == "Вторник" else 6

    # ищем ближайший нужный день
    offset = (day_index - start.weekday()) % 7
    first_date = start + timedelta(days=offset)

    # добавляем только нужные дни в пределах 2 недель
    for i in range(0, days, 7):  # шаг 7 дней — один и тот же день недели
        d = first_date + timedelta(days=i)
        label = d.strftime("%a %d.%m")
        cb = InlineKeyboardButton(label, callback_data=f"date_{d.isoformat()}")
        rows.append([cb])

    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_classes")])
    return InlineKeyboardMarkup(rows)

def build_time_keyboard():
    rows = [
        [
            InlineKeyboardButton("12:00 по Москве", callback_data="time_12:00 по Москве"),
            InlineKeyboardButton("16:00 по Москве", callback_data="time_16:00 по Москве")
        ],
        [InlineKeyboardButton("Отменить", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(rows)

# --- Хендлеры ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "Добро пожаловать в НЕшколу английского FoxEnglish 🦊\n"
            "Я помогу вам записаться на бесплатное онлайн занятие.\n\n"
            "Мы проводим бесплатные занятия по вторникам и воскресеньям. Какой день недели вам подходит?:",
            reply_markup=build_classes_keyboard()
        )
    return CHOOSING_CLASS

async def class_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    class_name = query.data.split("_", 1)[1]
    context.user_data["class_name"] = class_name
    await query.edit_message_text(
        f"Вы выбрали *{class_name}*.\nВыберите дату:",
        parse_mode="Markdown",
        reply_markup=build_dates_keyboard(class_name)
    )
    return CHOOSING_DATE

async def date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    date_iso = query.data.split("_", 1)[1]
    context.user_data["date"] = date_iso
    await query.edit_message_text(
        f"Дата: {date_iso}\nВыберите время:",
        reply_markup=build_time_keyboard()
    )
    return CHOOSING_TIME

async def time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    time_slot = query.data.split("_", 1)[1]
    context.user_data["time"] = time_slot
    await query.edit_message_text(
        f"Вы выбрали: {context.user_data['class_name']} — {context.user_data['date']} {time_slot}\n\n"
        "Введите ваше имя"
    )
    return ENTER_NAME

async def enter_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["name"] = name
    await update.message.reply_text(
        "Спасибо! Для вашего удобства мы заранее пришлём СМС напоминание о занятии.\n"
        "По какому номеру телефона вам направить СМС? (пример: +79991234567)."
    )
    return ENTER_PHONE

async def enter_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    context.user_data["phone"] = phone
    class_name = context.user_data["class_name"]
    date = context.user_data["date"]
    time_slot = context.user_data["time"]

    # Получаем юзернейм, если есть
    username = update.effective_user.username if update.effective_user.username else "-"

    # Проверяем вместимость
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM bookings WHERE class_name=? AND date=? AND time=?",
            (class_name, date, time_slot),
        )
        row = await cur.fetchone()
        count = row[0] if row else 0

    if count >= CAPACITY:
        await update.message.reply_text("Извините, этот слот уже заполнен. Попробуйте выбрать другую дату или время (/start).")
        return ConversationHandler.END

    # Добавляем запись
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO bookings (user_id, username, name, phone, class_name, date, time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                update.effective_user.id,
                username,
                context.user_data["name"],
                context.user_data["phone"],
                class_name,
                date,
                time_slot,
                datetime.utcnow().isoformat(),
            ),
        )
        await db.commit()
        booking_id = cur.lastrowid

    await update.message.reply_text(
        f"✅ Вы успешно записаны! Мы пришлём вам ссылку для подключения за 15 минут до начала\n"
        f"ID записи: {booking_id}\n"
        f"{class_name} {date} в {time_slot}"
    )

    # Уведомляем админа
    if ADMIN_CHAT_ID:
        admin_text = (
            f"🆕 Новая запись #{booking_id}\n"
            f"Пользователь: {update.effective_user.full_name} (@{username}) (@{update.effective_user.username})\n"
            f"Занятие: {class_name}\n"
            f"Дата/время: {date} {time_slot}\n"
            f"Имя: {context.user_data['name']}\n"
            f"Телефон: {context.user_data['phone']}"
        )
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text)

    return ConversationHandler.END

async def back_to_classes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Выберите занятие:", reply_markup=build_classes_keyboard())
    return CHOOSING_CLASS

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Действие отменено.")
    else:
        await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END

# --- дополнительные команды ---
async def mybookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, class_name, date, time, created_at FROM bookings WHERE user_id=? ORDER BY date", (uid,))
        rows = await cur.fetchall()
    if not rows:
        await update.message.reply_text("У вас нет записей.")
        return
    lines = [f"{r[0]}: {r[1]} — {r[2]} {r[3]} (создано {r[4]})" for r in rows]
    await update.message.reply_text("Ваши записи:\n" + "\n".join(lines))

async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("Нет доступа.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, user_id, name, phone, class_name, date, time FROM bookings ORDER BY date")
        rows = await cur.fetchall()
    if not rows:
        await update.message.reply_text("Записей нет.")
        return
    text = "\n".join([f"#{r[0]} {r[4]} {r[5]} {r[6]} — {r[2]} ({r[3]}) uid={r[1]}" for r in rows])
    await update.message.reply_text(text)

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ваш chat_id: {update.effective_chat.id}")

# --- main ---
def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.run(init_db())
    asyncio.run(cleanup_old_bookings())  # <-- добавлено автоочищение при запуске

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_CLASS: [CallbackQueryHandler(class_chosen, pattern="^class_")],
            CHOOSING_DATE: [
                CallbackQueryHandler(date_chosen, pattern="^date_"),
                CallbackQueryHandler(back_to_classes, pattern="^back_to_classes$"),
            ],
            CHOOSING_TIME: [
                CallbackQueryHandler(time_chosen, pattern="^time_"),
                CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
            ],
            ENTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_name)],
            ENTER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("mybookings", mybookings))
    app.add_handler(CommandHandler("admin_list", admin_list))
    app.add_handler(CommandHandler("myid", myid))

    asyncio.run(application.run_polling())

    #Запускаем фоновую задачу для напоминаний
    async def run():
        asyncio.create_task(send_reminders(app))
        await app.run_polling()

    asyncio.run(run())

if __name__ == "__main__":

    main()
