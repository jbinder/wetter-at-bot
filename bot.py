import csv
import json
import logging
import os
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
)

from chart import generate_weather_chart
from weather import AUSTRIAN_CITIES, get_weather, make_caption

load_dotenv()

logging.basicConfig(
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

VIENNA_TZ = ZoneInfo("Europe/Vienna")
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_FILE = DATA_DIR / "users.json"
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID: int | None = (
    int(os.environ["ADMIN_CHAT_ID"]) if os.environ.get("ADMIN_CHAT_ID") else None
)
DEFAULT_CITY = "Wien"
DEFAULT_TIME = "07:00"

HELP_TEXT = (
    "*Austria Weather Bot*\n\n"
    "I send you a daily weather chart for your chosen Austrian city.\n\n"
    "*Commands*\n"
    "/help — show this message\n"
    "/city — pick your city\n"
    "/time HH\\:MM — set daily notification time \\(e\\.g\\. `/time 07:30`\\)\n"
    "/weather — get today's chart right now\n"
    "/feedback — share a suggestion or report an issue\n\n"
    "*Chart shows*\n"
    "• Hourly temperature \\+ feels\\-like\n"
    "• Precipitation probability\n"
    "• UV index with WHO risk levels\n"
    "• Sunrise \\& sunset markers\n\n"
    "_All times are Europe/Vienna \\(CET/CEST\\)_"
)


# ── Access logging ────────────────────────────────────────────────────────────

ACCESS_LOG = DATA_DIR / "access.log"
FEEDBACK_LOG = DATA_DIR / "feedback.log"


def log_access(chat_id: int, action: str, detail: str = "", user=None) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ACCESS_LOG, "a", newline="") as f:
        csv.writer(f).writerow([
            datetime.now(VIENNA_TZ).isoformat(timespec="seconds"),
            chat_id,
            user.id if user else chat_id,
            action,
            detail,
        ])


# ── Persistence ───────────────────────────────────────────────────────────────

def load_users() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {}


def save_users(users: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(users, f, indent=2)


def get_user(users: dict, chat_id: int) -> dict:
    key = str(chat_id)
    if key not in users:
        users[key] = {"city": DEFAULT_CITY, "notification_time": DEFAULT_TIME}
        save_users(users)
    return users[key]


# ── Weather delivery ──────────────────────────────────────────────────────────

async def send_weather_photo(bot, chat_id: int, city: str) -> None:
    data = get_weather(city)
    buf = generate_weather_chart(data, city)
    caption = make_caption(data, city)
    await bot.send_photo(chat_id=chat_id, photo=buf, caption=caption)


async def daily_weather_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job.data
    chat_id = job["chat_id"]
    city = job["city"]
    try:
        await send_weather_photo(context.bot, chat_id, city)
        log_access(chat_id, "weather_daily", city)
    except Exception as exc:
        logger.error("Daily job failed for %s: %s", chat_id, exc)


# ── Scheduling ────────────────────────────────────────────────────────────────

def schedule_daily(app: Application, chat_id: int, city: str, time_str: str) -> None:
    hour, minute = map(int, time_str.split(":"))
    job_name = f"daily_{chat_id}"
    for job in app.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()
    app.job_queue.run_daily(
        daily_weather_job,
        time=dtime(hour=hour, minute=minute, tzinfo=VIENNA_TZ),
        name=job_name,
        data={"chat_id": chat_id, "city": city},
    )
    logger.info("Scheduled daily weather for %s at %s (%s)", chat_id, time_str, city)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    users = load_users()
    user = get_user(users, chat_id)
    schedule_daily(context.application, chat_id, user["city"], user["notification_time"])
    log_access(chat_id, "start", user=update.effective_user)
    await update.message.reply_text(
        f"👋 *Welcome to Austria Weather Bot\\!*\n\n"
        f"City: *{user['city']}*\n"
        f"Daily notification: *{user['notification_time']}* \\(Vienna time\\)\n\n"
        f"Use /help to see all commands\\.",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def cmd_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cities = list(AUSTRIAN_CITIES.keys())
    keyboard = []
    row: list = []
    for city in cities:
        row.append(InlineKeyboardButton(city, callback_data=f"city:{city}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    await update.message.reply_text(
        "🏙 *Select your city:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cb_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    city = query.data.split(":", 1)[1]
    chat_id = query.message.chat_id
    users = load_users()
    user = get_user(users, chat_id)
    user["city"] = city
    save_users(users)
    schedule_daily(context.application, chat_id, city, user["notification_time"])

    log_access(chat_id, "city_set", city, user=query.from_user)
    await query.edit_message_text(
        f"✅ City set to *{city}*\n"
        f"Daily notification at *{user['notification_time']}*\\.\n\n"
        f"Use /weather to get today's forecast now\\.",
    )


async def cmd_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "⏰ Please provide a time\\: `/time 07:30`",
        )
        return

    time_str = context.args[0]
    try:
        parts = time_str.split(":")
        if len(parts) != 2:
            raise ValueError
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid format\\. Use HH:MM — e\\.g\\. `/time 07:30`",
        )
        return

    normalized = f"{hour:02d}:{minute:02d}"
    chat_id = update.effective_chat.id
    users = load_users()
    user = get_user(users, chat_id)
    user["notification_time"] = normalized
    save_users(users)
    schedule_daily(context.application, chat_id, user["city"], normalized)
    log_access(chat_id, "time_set", normalized, user=update.effective_user)

    await update.message.reply_text(
        f"✅ Daily weather set to *{normalized}* \\(Vienna time\\)\n"
        f"City: *{user['city']}*",
    )


async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    users = load_users()
    user = get_user(users, chat_id)
    msg = await update.message.reply_text(f"⏳ Fetching weather for *{user['city']}*…")
    try:
        await send_weather_photo(context.bot, chat_id, user["city"])
        await msg.delete()
        log_access(chat_id, "weather_manual", user["city"], user=update.effective_user)
    except Exception as exc:
        await msg.edit_text(f"⚠️ Could not fetch weather: {exc}", parse_mode=None)


async def cmd_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text(
            "💬 Please include your message in the command:\n"
            "`/feedback Your message here`"
        )
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_LOG, "a", newline="") as f:
        csv.writer(f).writerow([
            datetime.now(VIENNA_TZ).isoformat(timespec="seconds"),
            chat_id,
            text,
        ])
    log_access(chat_id, "feedback", user=update.effective_user)
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"💬 Feedback from {chat_id}:\n\n{text}",
                parse_mode=None,
            )
        except Exception as exc:
            logger.warning("Could not notify admin of feedback: %s", exc)
    await update.message.reply_text(
        "✅ Thanks for your feedback\\! It helps improve the bot\\."
    )


# ── Startup hook ──────────────────────────────────────────────────────────────

async def post_init(app: Application) -> None:
    users = load_users()
    for chat_id_str, user in users.items():
        schedule_daily(
            app,
            int(chat_id_str),
            user.get("city", DEFAULT_CITY),
            user.get("notification_time", DEFAULT_TIME),
        )
    logger.info("Restored %d user schedule(s)", len(users))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .defaults(Defaults(parse_mode="MarkdownV2"))
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("city", cmd_city))
    app.add_handler(CommandHandler("time", cmd_time))
    app.add_handler(CommandHandler("weather", cmd_weather))
    app.add_handler(CommandHandler("feedback", cmd_feedback))
    app.add_handler(CallbackQueryHandler(cb_city, pattern=r"^city:"))

    logger.info("Bot starting…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
