# Economic News Bot (English)

بات خبری اقتصادی که هر ۳۰ دقیقه فیدهای RSS چند منبع معتبر خبری جهانی رو
چک می‌کنه، با Gemini تشخیص می‌ده کدوم خبر واقعاً مهمه، و اگه مهم بود
یه پست انگلیسی (عنوان + خلاصه + عکس در صورت وجود) توی کانال تلگرام
پست می‌کنه.

## منابع خبری فعلی

- Wall Street Journal (World News)
- Fox Business (Economy + Markets)
- CNBC (Economy)
- MarketWatch / Dow Jones (Markets Main)
- Investing.com (Forex)
- Washington Post (Business)
- New York Times (Business)
- BBC (Business)

## راه‌اندازی

### ۱. کلید Gemini بگیر

از [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
یه کلید رایگان بساز.

### ۲. یه ربات تلگرام بساز

با [@BotFather](https://t.me/BotFather) توی تلگرام یه ربات جدید بساز و
توکنش رو نگه دار. بعد اون ربات رو به‌عنوان ادمین به کانالت اضافه کن.

### ۳. کد رو ویرایش کن

توی `bot.py` این دو خط رو با مقادیر واقعی کانالت جایگزین کن:

```python
PINNED_PRICE_LINK = "https://t.me/REPLACE_WITH_CHANNEL/1"
CHANNEL_HANDLE = "@REPLACE_WITH_CHANNEL"
```

### ۴. این ریپو رو توی گیت‌هاب بساز و آپلود کن

فایل‌های این پوشه رو مستقیم توی یه ریپوی جدید (خالی) توی گیت‌هاب push کن.

### ۵. Secrets رو تنظیم کن

توی مسیر **Settings → Secrets and variables → Actions** این سه‌تا رو اضافه کن:

| Secret | مقدار |
|---|---|
| `BOT_TOKEN` | توکن رباتی که از BotFather گرفتی |
| `CHANNEL_ID` | آیدی کانال، مثلاً `@my_channel` یا `-100xxxxxxxxxx` |
| `GEMINI_API_KEY` | کلید Gemini که از AI Studio گرفتی |

### ۶. Workflow permissions رو فعال کن

توی **Settings → Actions → General → Workflow permissions**، گزینه‌ی
**Read and write permissions** رو انتخاب و Save کن (تا بات بتونه
`posted.json` رو کامیت کنه).

### ۷. اجرا کن

برو تب **Actions**، روی workflow به اسم `Economic News Bot` کلیک کن و
دکمه‌ی **Run workflow** رو بزن. از این به بعد هر ۳۰ دقیقه خودکار اجرا می‌شه.

## نکات

- هر خبری که یک‌بار بررسی یا پست بشه، لینکش توی `posted.json` ذخیره
  می‌شه تا دوباره پست نشه.
- حداکثر ۵ پست در هر اجرا و حداکثر ۲۵ خبر بررسی‌شده در هر اجرا
  (برای رعایت quota رایگان Gemini) — این عددها رو می‌تونی توی بالای
  `bot.py` تغییر بدی.
- این بات یک نسخه‌ی کاملاً مستقل و انگلیسی‌زبانه؛ به هیچ پروژه یا
  کانال دیگه‌ای وابسته نیست.
