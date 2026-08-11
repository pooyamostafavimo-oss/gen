#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
World Economic News Bot -> Telegram Channel (English)
Each run: checks the economic RSS feeds, finds new important news,
grabs the news image (if available) and posts an English caption to
the Telegram channel. Already-posted links are stored in posted.json
so nothing gets posted twice.
"""

import os
import re
import json
import time
import html
import feedparser
import requests

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

BOT_TOKEN = os.environ["BOT_TOKEN"]          # read from GitHub Secrets
CHANNEL_ID = os.environ["CHANNEL_ID"]        # e.g. @my_econ_news or -100xxxxxxxxxx
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]  # free key from aistudio.google.com/app/apikey

GEMINI_MODEL = "gemini-flash-lite-latest"   # Google's always-current alias for the latest stable flash-lite model
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
)

POSTED_FILE = "posted.json"
MAX_POSTED_HISTORY = 500     # max number of stored links (keeps the file from growing forever)
MAX_POSTS_PER_RUN = 5        # max number of posts sent per run
MAX_CANDIDATES_PER_RUN = 25  # max number of news items sent to Gemini per run (to respect the free quota)

# Global economic RSS feeds (free, no API key required)
# Note: Bloomberg, Reuters, and ForexFactory no longer offer official free
# RSS feeds, so credible equivalents are used instead (CNBC for Bloomberg,
# MarketWatch/Dow Jones for Reuters, Investing.com Forex for ForexFactory)
RSS_FEEDS = [
    "https://feeds.a.dj.com/rss/RSSWorldNews.xml",             # Wall Street Journal - World News
    "https://moxie.foxbusiness.com/google-publisher/economy.xml",  # Fox Business - Economy
    "https://moxie.foxbusiness.com/google-publisher/markets.xml",  # Fox Business - Markets
    "https://www.cnbc.com/id/20910258/device/rss/rss.html",    # CNBC Economy (Bloomberg substitute)
    "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",  # MarketWatch/Dow Jones (Reuters substitute)
    "https://www.investing.com/rss/news_285.rss",              # Investing.com Forex (ForexFactory substitute)
    "https://feeds.washingtonpost.com/rss/business",           # Washington Post - Business
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",  # New York Times - Business
    "https://feeds.bbci.co.uk/news/business/rss.xml",          # BBC - Business
]


def ask_gemini(title, summary):
    """
    Asks Gemini whether the news is important, and if so, returns a clean
    short English title/summary. Output: dict or None (on error)
    """
    prompt = f"""You are an economic news assistant. Review this news item:

Title: {title}
Summary: {summary}

Only mark this news as important if it's genuinely significant for the
general economic public (e.g. central bank decisions, interest rates,
inflation, major stock/currency/gold/oil market swings, economic
crises, major decisions by governments or large companies). Ordinary,
low-significance news is NOT important.

Return ONLY raw JSON output (no ```json fences, no extra explanation) with this structure:
{{"important": true or false, "title_en": "clean, concise English title", "summary_en": "concise English summary in max 2 sentences"}}
"""
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        resp = requests.post(GEMINI_URL, json=body, timeout=30)
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = text.strip().strip("```").replace("json\n", "", 1).strip()
        return json.loads(text)
    except Exception as e:
        print(f"⚠️ Error calling Gemini: {e}")
        return None


def load_posted():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_posted(posted_list):
    trimmed = posted_list[-MAX_POSTED_HISTORY:]
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


def clean_html(raw):
    """Strips HTML tags from the news summary"""
    text = re.sub(r"<[^>]+>", "", raw or "")
    return html.unescape(text).strip()


def extract_image(entry):
    """Tries to find the news image URL from the RSS feed entry"""
    if "media_content" in entry and entry.media_content:
        return entry.media_content[0].get("url")
    if "media_thumbnail" in entry and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")
    if "links" in entry:
        for link in entry.links:
            if link.get("type", "").startswith("image"):
                return link.get("href")
    match = re.search(r'<img[^>]+src="([^"]+)"', entry.get("summary", ""))
    if match:
        return match.group(1)
    return None


# TODO: replace these two with your real channel details
PINNED_PRICE_LINK = "https://t.me/REPLACE_WITH_CHANNEL/1"   # link to the pinned live-price message in your channel
CHANNEL_HANDLE = "@REPLACE_WITH_CHANNEL"                    # your channel's public handle


def send_to_telegram(title_en, link, summary_en, image_url):
    caption = f"📌 <b>{html.escape(title_en)}</b>\n\n"
    caption += f'<b>💰 Click <a href="{PINNED_PRICE_LINK}">here</a> for live prices</b>\n\n'
    if summary_en:
        short_summary = summary_en[:500] + ("..." if len(summary_en) > 500 else "")
        caption += f"{html.escape(short_summary)}\n\n"
    caption += f'🔗 <a href="{link}">Read the full article</a>\n\n'
    caption += CHANNEL_HANDLE

    if image_url:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": CHANNEL_ID,
            "photo": image_url,
            "caption": caption[:1024],
            "parse_mode": "HTML",
        }
        resp = requests.post(url, data=payload, timeout=30)
        if resp.status_code == 200 and resp.json().get("ok"):
            return True
        print(f"⚠️ Sending with photo failed, retrying without photo... ({resp.text[:200]})")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": caption[:4096],
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, data=payload, timeout=30)
    if resp.status_code == 200 and resp.json().get("ok"):
        return True
    print(f"❌ Sending message failed: {resp.text[:300]}")
    return False


def main():
    posted = load_posted()
    posted_set = set(posted)
    new_posts_count = 0
    candidates_checked = 0

    for feed_url in RSS_FEEDS:
        if new_posts_count >= MAX_POSTS_PER_RUN or candidates_checked >= MAX_CANDIDATES_PER_RUN:
            break
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"⚠️ Error reading feed {feed_url}: {e}")
            continue

        for entry in feed.entries:
            if new_posts_count >= MAX_POSTS_PER_RUN or candidates_checked >= MAX_CANDIDATES_PER_RUN:
                break

            link = entry.get("link")
            title = entry.get("title", "")
            if not link or not title:
                continue
            if link in posted_set:
                continue

            summary = clean_html(entry.get("summary", ""))
            candidates_checked += 1

            result = ask_gemini(title, summary)
            if not result or not result.get("important"):
                posted.append(link)
                posted_set.add(link)
                continue

            title_en = result.get("title_en", title)
            summary_en = result.get("summary_en", "")
            image_url = extract_image(entry)

            print(f"📤 Posting: {title_en}")
            success = send_to_telegram(title_en, link, summary_en, image_url)

            posted.append(link)
            posted_set.add(link)
            if success:
                new_posts_count += 1
                time.sleep(2)

    save_posted(posted)
    print(f"✅ Run finished. Checked: {candidates_checked} | Posted: {new_posts_count}")


if __name__ == "__main__":
    main()
