
import os
import pandas as pd
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, CallbackContext
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

TOKEN = os.environ.get("BOT_TOKEN")
bot = Bot(token=TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot, None, use_context=True)

PREVIOUS_FILE = "previous.xlsx"
LATEST_FILE = "latest.xlsx"

def start(update: Update, context: CallbackContext):
    update.message.reply_text("Привіт! Надішли Excel-файл (.xlsx), і я порівняю його з попереднім.")

def handle_file(update: Update, context: CallbackContext):
    document = update.message.document
    if not document.file_name.endswith('.xlsx'):
        update.message.reply_text("Будь ласка, надішли Excel-файл з розширенням .xlsx")
        return

    file = document.get_file()
    file.download(LATEST_FILE)

    if not os.path.exists(PREVIOUS_FILE):
        os.rename(LATEST_FILE, PREVIOUS_FILE)
        update.message.reply_text("Перший файл збережено. Надішли ще один для порівняння.")
        return

    text = get_diff_text(pd.read_excel(PREVIOUS_FILE), pd.read_excel(LATEST_FILE))
    context.user_data['post_text'] = text

    keyboard = [[
        InlineKeyboardButton("✅ Публікувати", callback_data='publish'),
        InlineKeyboardButton("📝 Редагувати", callback_data='edit'),
        InlineKeyboardButton("❌ Скасувати", callback_data='cancel')
    ]]
    update.message.reply_text(text or "Змін не знайдено.", reply_markup=InlineKeyboardMarkup(keyboard))

    os.replace(LATEST_FILE, PREVIOUS_FILE)

def get_diff_text(old_df, new_df):
    try:
        old_df.columns = ["Назва", "Регіон", "Ціна", "Публікувати"]
        new_df.columns = ["Назва", "Регіон", "Ціна", "Публікувати"]

        old_df["Ціна"] = pd.to_numeric(old_df["Ціна"], errors="coerce")
        new_df["Ціна"] = pd.to_numeric(new_df["Ціна"], errors="coerce")
        old_df["Назва"] = old_df["Назва"].str.strip()
        new_df["Назва"] = new_df["Назва"].str.strip()
        old_df["Регіон"] = old_df["Регіон"].str.strip()
        new_df["Регіон"] = new_df["Регіон"].str.strip()

        old_df["id"] = old_df["Назва"] + " | " + old_df["Регіон"]
        new_df["id"] = new_df["Назва"] + " | " + new_df["Регіон"]

        merged = pd.merge(old_df, new_df, on="id", how="outer", suffixes=("_старе", "_нове"))
        merged["Δ"] = merged["Ціна_нове"] - merged["Ціна_старе"]

        def status(row):
            if pd.isna(row["Ціна_старе"]):
                return "🆕"
            elif row["Δ"] > 0:
                return "🔼"
            elif row["Δ"] < 0:
                return "🔽"
            elif str(row.get("Публікувати_нове", "")).strip() == "+":
                return "✅"
            else:
                return None

        merged["Статус"] = merged.apply(status, axis=1)
        filtered = merged[merged["Статус"].notna()].copy()

        lines = []
        for _, row in filtered.iterrows():
            name = row.get("Назва_нове") or row.get("Назва_старе")
            region = row.get("Регіон_нове") or row.get("Регіон_старе")
            price = row.get("Ціна_нове")
            mark = row["Статус"]
            lines.append(f"{mark} {name} | {region}: {price:.0f} грн з ПДВ")

        today = datetime.now().strftime("%d.%m.%Y")
        message_lines = []
        message_lines.append(f"Доброго дня! ТОВ "Хиллс Трейд", Оновлення цін на {today}:")
        message_lines.append("")
        message_lines.extend(lines)
        message_lines.append("")
        message_lines.append("Можлива доставка у ваш регіон або склад, за деталями звертайтесь до менеджера.")
        message_lines.append("")
        message_lines.append("Контакти менеджерів:")
        message_lines.append("📞 Інна — +38 (095) 502-22-87 • @kipish_maker2")
        message_lines.append("📞 Павло — +38 (067) 519-36-86 • @Pawa_fbc")
        message_lines.append("📧 office@hillstrade.com.ua")

        return "
".join(message_lines)

    except Exception as e:
        return f"Помилка під час обробки: {e}"

def handle_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    if data == 'publish':
        text = context.user_data.get('post_text', '')
        if text:
            for channel_id in os.environ.get("CHANNEL_IDS", "").split(","):
                try:
                    bot.send_message(chat_id=int(channel_id.strip()), text=text)
                except Exception as e:
                    print(f"Помилка надсилання в канал {channel_id}: {e}")
            query.edit_message_text("✅ Опубліковано.")
    elif data == 'edit':
        query.edit_message_text("✏️ Надішли новий текст для публікації.")
    elif data == 'cancel':
        query.edit_message_text("❌ Скасовано.")

def handle_edit(update: Update, context: CallbackContext):
    context.user_data['post_text'] = update.message.text
    keyboard = [[
        InlineKeyboardButton("✅ Публікувати", callback_data='publish'),
        InlineKeyboardButton("❌ Скасувати", callback_data='cancel')
    ]]
    update.message.reply_text("Оновлений текст збережено. Підтвердь публікацію:", reply_markup=InlineKeyboardMarkup(keyboard))

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.document.file_extension("xlsx"), handle_file))
dispatcher.add_handler(CallbackQueryHandler(handle_callback))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_edit))

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

@app.route("/")
def index():
    return "Бот працює!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
