
import os
import feedparser
import telebot
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from bs4 import BeautifulSoup
import requests
import json

TOKEN = "7768675792:AAGwjrIvx2LaYVWBekcMRqeMayydMLmUf5s"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "40152158"))
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1002591966680"))
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "agroscan_secret")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

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
    return soup.get_text().strip()

def fetch_latifundist():
    url = "https://latifundist.com/novosti"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers, timeout=10)
    print("LATIFUNDIST RESPONSE SAMPLE:", response.text[:300])
    soup = BeautifulSoup(response.text, 'html.parser')
    news_blocks = soup.select(".news-block__title a")
    new_items = []

    for block in news_blocks[:5]:
        title = block.get_text(strip=True)
        link = "https://latifundist.com" + block['href']
        if link not in SEEN_LINKS:
            SEEN_LINKS.add(link)
            new_items.append({
                'title': title,
                'link': link,
                'desc': 'Новина з Latifundist',
                'source': 'latifundist.com'
            })
    return new_items

def fetch_agronews():
    feed = feedparser.parse("https://agronews.ua/rss")
    new_items = []
    for entry in feed.entries[:5]:
        if entry.link not in SEEN_LINKS:
            SEEN_LINKS.add(entry.link)
            description = clean_html(entry.summary) if hasattr(entry, 'summary') else 'Новина з Agronews RSS'
            new_items.append({
                'title': entry.title,
                'link': entry.link,
                'desc': description,
                'source': 'agronews.ua'
            })
    return new_items

def fetch_all_news():
    all_news = []
    all_news += fetch_agronews()
    all_news += fetch_latifundist()
    save_seen_links(SEEN_LINKS)
    return all_news

def format_post(news):
    source_tag = "#agronews" if "agronews" in news["source"] else "#latifundist"
    date_str = datetime.now().strftime("%d.%m.%Y")
    post = (
        "AgroScan - Новина з {source}\n\n"
        "*{title}*\n\n"
        "{desc}\n\n"
        "Дата: {date}\n"
        "Джерело: [{source}]({link})\n"
        "{link}\n\n"
        "{tag} #агроновини #agroscan"
    ).format(
        source=news["source"],
        title=news["title"],
        desc=news["desc"],
        date=date_str,
        link=news["link"],
        tag=source_tag
    )
    return post

def send_drafts():
    news_items = fetch_all_news()
    if not news_items:
        bot.send_message(ADMIN_ID, "Інфо: Новин не знайдено.")
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

@bot.message_handler(commands=['check_now', 'перевірити', 'update'])
def manual_check_command(message):
    bot.send_message(message.chat.id, "🔄 Перевірка новин розпочата...")
    send_drafts()

@app.route(f"/{WEBHOOK_SECRET}", methods=["POST"])
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
