
import os
import feedparser
import telebot
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from bs4 import BeautifulSoup
import json
import re

# Новый токен для AgroScan News Bot
TOKEN = "7768675792:AAGwjrIvx2LaYVWBekcMRqeMayydMLmUf5s"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "40152158"))
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1002591966680"))
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "agroscan_secret")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

RSS_FEEDS = ['https://agronews.ua/rss', 'https://latifundist.com/rss/news']
SEEN_LINKS_FILE = "seen_links.json"
AWAITING_EDIT = {}
LINK_CACHE = {}

def load_seen_links():
    if os.path.exists(SEEN_LINKS_FILE):
        with open(SEEN_LINKS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen_links(links):
    with open(SEEN_LINKS_FILE, "w") as f:
        json.dump(list(links), f)

SEEN_LINKS = load_seen_links()

def clean_html(text):
    soup = BeautifulSoup(text, 'html.parser')
    clean = soup.get_text()
    clean = re.sub(r'Continue Reading.*', '', clean).strip()
    return clean

def fetch_latest_news():
    items = []
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        items.extend(feed.entries)
    new_items = []
    for entry in items[:10]:
        if entry.link not in SEEN_LINKS:
            SEEN_LINKS.add(entry.link)
            description = clean_html(entry.summary) if hasattr(entry, 'summary') else 'Новина з Agronews RSS'
            new_items.append({
                'title': entry.title,
                'link': entry.link,
                'desc': description,
                'source': entry.link.split('/')[2]
            })
    save_seen_links(SEEN_LINKS)
    return new_items

def format_post(news):
    source_tag = '#agronews' if 'agronews' in news['source'] else '#latifundist'
    return f"""🌾 AgroScan — Новина з Agronews

*{news['title']}*

{news['desc']}

🗓 Дата: {datetime.now().strftime('%d.%m.%Y')}
🔗 Джерело: [Agronews.ua]({news['link']})
{news['link']}

{source_tag} #агроновини #agroscan
"""

def send_drafts():
    news_items = fetch_latest_news()
    if not news_items:
        return
    for news in news_items:
        post = format_post(news)
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(
            telebot.types.InlineKeyboardButton("✅ Публікувати", callback_data='post'),
            telebot.types.InlineKeyboardButton("❌ Відхилити", callback_data='cancel'),
            telebot.types.InlineKeyboardButton("📝 Редагувати", callback_data='edit')
        )
        msg = bot.send_message(ADMIN_ID, post, parse_mode="Markdown", reply_markup=markup)
        LINK_CACHE[msg.chat.id] = news['link']

@bot.callback_query_handler(func=lambda call: call.data in ['post', 'cancel', 'edit'])
def handle_decision(call):
    if call.data == 'post':
        text = call.message.text
        bot.send_message(CHANNEL_ID, text, parse_mode="Markdown")
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="✅ Опубліковано")
    elif call.data == 'cancel':
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="❌ Скасовано")
    elif call.data == 'edit':
        AWAITING_EDIT[call.message.chat.id] = call.message.message_id
        bot.send_message(call.message.chat.id, "✍️ Надішли мені новий текст посту, і я автоматично додам посилання на джерело.")

@bot.message_handler(func=lambda message: message.chat.id in AWAITING_EDIT)
def handle_edit(message):
    original_id = AWAITING_EDIT.pop(message.chat.id)
    link = LINK_CACHE.pop(message.chat.id, '')
    full_text = message.text.strip()
    if link and link not in full_text:
        full_text += f"\n\n{link}"
    bot.send_message(CHANNEL_ID, full_text, parse_mode="Markdown")
    bot.edit_message_text(chat_id=message.chat.id, message_id=original_id, text="✅ Опубліковано після редагування")

@app.route("/agroscan_secret", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.get_json(force=True))
    bot.process_new_updates([update])
    return "ok"

@app.route("/")
def index():
    return "AgroScan новинний бот працює."

if __name__ == "__main__":
    scheduler.add_job(send_drafts, "interval", hours=1)
    app.run(host="0.0.0.0", port=10000)
