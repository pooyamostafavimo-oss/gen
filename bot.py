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

# One or more free keys from aistudio.google.com/app/apikey.
# Preferred: set GEMINI_API_KEYS as a comma-separated list, e.g. "key1,key2,key3".
# Still supported: a single GEMINI_API_KEY. If both are set, GEMINI_API_KEYS wins.
_keys_raw = os.environ.get("GEMINI_API_KEYS") or os.environ["GEMINI_API_KEY"]
GEMINI_API_KEYS = [k.strip() for k in _keys_raw.split(",") if k.strip()]

GEMINI_MODEL = "gemini-flash-lite-latest"   # Google's always-current alias for the latest stable flash-lite model


def _gemini_url(api_key):
    return (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={api_key}"
    )


POSTED_FILE = "posted.json"
MAX_POSTED_HISTORY = 500     # max number of stored links (keeps the file from growing forever)
MAX_POSTS_PER_RUN = 5        # max number of posts sent per run
MAX_CANDIDATES_PER_RUN = 25  # max number of news items sent to Gemini per run (to respect the free quota)
GEMINI_CALL_DELAY = 3        # seconds to wait between Gemini calls (spreads out requests -> avoids RPM limit)

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

If it's important, write a FULL, self-contained summary that completely
replaces the need to read the original article. Do not write a teaser
or a short blurb - write a thorough news brief, roughly 8-14 sentences
(can be longer if the story genuinely has that much substance), that
covers:
- what happened, exactly (all key facts and figures - percentages,
  dollar amounts, dates, names of people/institutions/countries)
- the immediate context and background needed to understand it
- what caused it / what led up to it, if relevant
- reactions from officials, markets, or experts, if mentioned in the
  source
- why it matters and what the likely effects or next steps are

Use the full Summary text provided below as your source material and
extract every relevant detail from it - don't leave out facts just to
keep it short. The goal is that a reader finishes your summary knowing
everything a reader of the original article would know, and never
needs to click through.

Return ONLY raw JSON output (no ```json fences, no extra explanation) with this structure:
{{"important": true or false, "title_en": "clean, concise English title", "summary_en": "full self-contained English news brief, ~8-14 sentences, covering every key fact from the source"}}
"""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 1024},
    }

    last_error = None
    # Try each key once per pass. If every key is rate-limited (429), wait a
    # bit and do one more pass over all keys before giving up on this item.
    for attempt in range(2):
        for key_index, api_key in enumerate(GEMINI_API_KEYS):
            try:
                resp = requests.post(_gemini_url(api_key), json=body, timeout=30)
                if resp.status_code == 429:
                    last_error = f"429 Too Many Requests (key #{key_index + 1})"
                    print(f"⚠️ Gemini rate limit on key #{key_index + 1}, trying next key...")
                    continue  # move on to the next key immediately
                resp.raise_for_status()
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                text = text.strip().strip("```").replace("json\n", "", 1).strip()
                return json.loads(text)
            except Exception as e:
                last_error = e
                print(f"⚠️ Error calling Gemini with key #{key_index + 1}: {e}")
                continue

        if attempt == 0:
            print("⏳ All keys rate-limited, waiting 20s before one retry pass...")
            time.sleep(20)

    print(f"⚠️ Gemini call failed after trying all {len(GEMINI_API_KEYS)} key(s): {last_error}")
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


CHANNEL_HANDLE = "@GlobalEconoNews"                    # your channel's public handle
CHANNEL_LINK = "https://t.me/GlobalEconoNews"          # your channel's public link


TELEGRAM_PHOTO_CAPTION_LIMIT = 1024
TELEGRAM_MESSAGE_LIMIT = 4096


def _send_telegram_request(method, payload):
    """Sends a Telegram API request. Returns the response's `result` dict on
    success (so callers can grab e.g. message_id), or None on failure."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    resp = requests.post(url, data=payload, timeout=30)
    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code == 200 and data.get("ok"):
        return data.get("result")
    print(f"❌ Telegram {method} failed: {resp.text[:300]}")
    return None


def _split_text(text, limit):
    """Splits long text into <= limit-sized chunks, breaking on paragraph/line
    boundaries where possible so no sentence gets cut mid-word."""
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut == -1:
            cut = remaining.rfind(" ", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def send_to_telegram(title_en, link, summary_en, image_url):
    header = f"📌 <b>{html.escape(title_en)}</b>\n\n"
    body_text = html.escape(summary_en) if summary_en else ""
    footer = (
        f'\n\n🔗 <a href="{link}">Read the full article</a>\n\n'
        f'<a href="{CHANNEL_LINK}">{CHANNEL_HANDLE}</a>'
    )

    full_text = f"{header}{body_text}{footer}"

    # If it fits inside a single photo caption, post it as one message
    # with the photo attached - the ideal, simplest case.
    if image_url and len(full_text) <= TELEGRAM_PHOTO_CAPTION_LIMIT:
        payload = {
            "chat_id": CHANNEL_ID,
            "photo": image_url,
            "caption": full_text,
            "parse_mode": "HTML",
        }
        if _send_telegram_request("sendPhoto", payload):
            return True
        print("⚠️ Sending with photo failed, retrying without photo...")
        image_url = None  # fall through to text-only below

    # Summary too long for a photo caption: send the photo first (title as
    # caption), then reply to that same photo message with the full summary
    # so Telegram threads them together as one visual post instead of two
    # unrelated messages.
    photo_message_id = None
    if image_url:
        payload = {
            "chat_id": CHANNEL_ID,
            "photo": image_url,
            "caption": header.strip(),
            "parse_mode": "HTML",
        }
        result = _send_telegram_request("sendPhoto", payload)
        if result:
            photo_message_id = result.get("message_id")
        else:
            print("⚠️ Sending photo failed, continuing with text only...")

    if photo_message_id:
        text_body = f"{body_text}{footer}".strip()  # title already sent with photo
    else:
        text_body = full_text

    ok_overall = True
    for i, chunk in enumerate(_split_text(text_body, TELEGRAM_MESSAGE_LIMIT)):
        payload = {
            "chat_id": CHANNEL_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        if i == 0 and photo_message_id:
            payload["reply_to_message_id"] = photo_message_id
        if not _send_telegram_request("sendMessage", payload):
            ok_overall = False
        time.sleep(1)

    return bool(photo_message_id) or ok_overall

    return True


def main():
    print(f"🔑 Loaded {len(GEMINI_API_KEYS)} Gemini API key(s)")
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

            if candidates_checked > 1:
                time.sleep(GEMINI_CALL_DELAY)  # spread requests out to avoid RPM limit

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
