# kill_pv2 v2 — پنل VLESS روی GitHub Actions

پنل مدیریت کانفیگ VLESS (WS+TLS پشت Cloudflare Tunnel) که روی GitHub Actions اجرا می‌شود؛ بازنویسی کامل نسخهٔ قبلی با UI جدید، NoAds هوشمند، بای‌پس ایران، حسابداری دقیق ترافیک، تاریخچهٔ رمزنگاری‌شده و امنیت ورود.

## ✅ امکانات پیاده‌سازی‌شده

| بخش | توضیح |
|---|---|
| **ویرایش کامل کانفیگ** | تغییر نام، حجم (تنظیم دقیق / افزودن / کم‌کردن / نامحدود)، زمان (روز+ساعت / افزودن روز / ریست)، آی‌پی تمیز، یادداشت، NoAds، بای‌پس، حد IP، صفر کردن مصرف، UUID جدید، تغییر مصرف‌شده |
| **حسابداری دقیق** | بایت‌ها مستقیم از `Xray Stats API` (user>>>uplink/downlink) هر ۲ ثانیه با reset خوانده می‌شود → بدون تخمین، بدون عدد رندوم. هدر `Subscription-Userinfo` در ساب. |
| **NoAds هوشمند** | ۴ لایه: لیست یوتیوب/گوگل + شبکه‌های جهانی + تبلیغات ایرانی، لیست محافظت‌شده (googlevideo، تلگرام، گیم‌ها…)، `geosite:category-ads-all`، و regex هوشمند روی ساب‌دامنه (ads./pagead2./rtb./…). سه سطح off/balanced/aggressive + لیست سفارشی + سفید + تست زنده. **هم سمت سرور (routing Xray) هم سمت کلاینت (ساب JSON)**. |
| **بای‌پس ایران** | دامنه‌های `.ir`، `geosite:category-ir`، `geoip:ir` و ~۹۰ سرویس اصلی (بانک، اسنپ، دیجی‌کالا…) بدون VPN؛ لیست سفارشی مستقیم/اجباری-VPN؛ تست مسیر. |
| **بهینه‌سازی شبکه** | BBR+fq، بافرهای بزرگ، keepalive کوتاه، TFO، MTU probing، nginx با epoll/65k conn، cloudflared h2 و IPv4؛ Xray: `tcpNoDelay`، `bufferSize 4`، sniffing QUIC، DNS-over-HTTPS، UseIPv4. ساب Smart: **Balancer leastPing** روی پول آی‌پی تمیز + **TLS fragment** برای ساعات شلوغ. |
| **تاریخچهٔ رمزنگاری‌شده** | هر کانفیگ → لیست IPها → سایت‌های هر IP (با فیلتر). ذخیره در SQLite، پایدار بعد از ریست/رفرش، در `data/vault.enc` با **AES-256-GCM + scrypt** کامیت می‌شود. خروجی `.kpv2` رمزنگاری‌شده. |
| **امنیت ورود** | رمز از سکرت `PANEL_PASS` (نه رندوم). ۵ تلاش اشتباه → قفل ۱۵ دقیقه، تأخیر تصاعدی، `hmac.compare_digest`، کوکی HttpOnly/SameSite. |
| **مسیر مخفی** | `/` فقط `service is active` می‌دهد؛ پنل روی `/KILLPV2`. |
| **UI سبک** | HTML/CSS/JS خالص بدون CDN (۴۰KB)، ۶ تب مجزا، موبایل‌فرست، روی گوشی ضعیف هم روان. |
| **دیتابیس** | SQLite با WAL، جدول‌های clients/traffic_samples/client_ips/visits/events/login_attempts؛ مهاجرت خودکار از `panel_db.json` قدیمی. |

## 🔗 مسیرها

| مسیر | توضیح |
|---|---|
| `https://<tunnel>/` | «service is active» |
| `https://<tunnel>/KILLPV2` | پنل |
| `https://<tunnel>/sub/<name>` | ساب base64 (v2rayNG/Hiddify) |
| `https://<tunnel>/sub/<name>.json` | ساب Smart Xray JSON (balancer + fragment + NoAds + bypass) |
| `https://<tunnel>/sub/<name>.sb.json` | ساب sing-box |
| `raw.githubusercontent.com/<repo>/main/sub_links/<name>[.json|.sb.json]` | همان سه فایل، **دائمی** روی GitHub (هر ۶۰ ثانیه آپدیت) |

API پنل زیر `/KILLPV2/api/*`: `login, logout, overview, clients (GET/POST/PUT/DELETE, /toggle, /links), history/<n> (+/visits?ip=&q=, +/export), traffic/<n>?hours=, noads, bypass, settings, logs, apply`.

## 🔐 سکرت‌های GitHub (Settings → Secrets → Actions)

| نام | الزامی | توضیح |
|---|---|---|
| `PANEL_PASS` | ✅ | رمز پنل (ثابت). اگر خالی باشد رمز موقت در لاگ اکشن چاپ می‌شود. |
| `PANEL_USER` | — | پیش‌فرض `admin` |
| `DB_ENCRYPTION_KEY` | توصیه‌شده | کلید رمزنگاری vault/تاریخچه. اگر نباشد از `PANEL_PASS` مشتق می‌شود. **تغییرش = از دست رفتن تاریخچه.** |
| `GH_PAT` | ✅ | برای لوپ اجرای مجدد ورک‌فلو (مثل قبل) |

## 🚀 راه‌اندازی
1. سکرت‌ها را تنظیم کن.
2. Actions → *Automated Core Data Synchronization* → Run workflow.
3. در لاگ مرحلهٔ *Launch Operational Backend Microservice* آدرس `https://xxx.trycloudflare.com/KILLPV2` چاپ می‌شود.
4. کاربر قدیمی `pvp_HS` از `panel_db.json` به‌صورت خودکار مهاجرت می‌کند و بعد از آن فقط `data/vault.enc` (رمزنگاری‌شده) در ریپو می‌ماند.

### راهنمای کاربر نهایی
- **ساب ساده:** لینک GitHub را در v2rayNG / Hiddify اضافه کن (مصرف/باقی‌مانده/زمان داخل ساب نمایش داده می‌شود).
- **ساب Smart (پیشنهادی برای ساعات شلوغ و گیم):** `...sub_links/<name>.json` را در v2rayNG → *Custom config* یا Hiddify ایمپورت کن → خودکار سریع‌ترین آی‌پی تمیز، فرگمنت TLS، حذف تبلیغات و باز شدن سایت‌های ایرانی بدون VPN.

## 🧪 تست‌های انجام‌شده (در سندباکس با Xray واقعی)
- ۵ رمز اشتباه → `429 locked`؛ رمز درست در حالت قفل هم رد می‌شود ✅
- ایجاد / نام تکراری (409) / نام نامعتبر (400) / تغییر نام / افزودن حجم / تنظیم دقیق MB / نامحدود / toggle ✅
- دانلود ۱MB واقعی از طریق تانل → `down=1,071,133` بایت ثبت شد (دقیق) ✅
- `pagead2.googlesyndication.com`, `googleads.g.doubleclick.net`, `yektanet.com` → مسدود؛ `youtube.com` → 204 ✅
- تاریخچه: IP `5.112.33.44` → ۶ دامنه با پرچم blocked ✅؛ خروجی `.kpv2` رمزگشایی شد ✅
- محدودیت حجم: عبور از 1.5MB → EXPIRED و اتصال قطع؛ افزودن حجم → خودکار فعال ✅
- ریستارت → همهٔ داده و تاریخچه از vault برگشت ✅
- UI headless (390px موبایل): لاگین، ساخت، ویرایش، لینک‌ها، تاریخچه، NoAds، بای‌پس، حذف — بدون خطای JS ✅

## 📁 ساختار
```
analytics_worker.py        # entrypoint (سازگار با ورک‌فلو)
killpv2/
  app.py          # orchestrator: xray, poller, tailer, git sync
  server.py       # HTTP panel + REST API (/KILLPV2)
  xray.py         # config بهینه، Stats API، log tail
  store.py        # SQLite + vault رمزنگاری‌شده + مهاجرت legacy
  crypto.py       # AES-256-GCM / scrypt
  noads.py        # موتور NoAds
  bypass.py       # موتور بای‌پس ایران
  subscription.py # base64 / Xray JSON / sing-box
  web/            # index.html, app.css, app.js (بدون وابستگی)
data/vault.enc    # اسنپ‌شات رمزنگاری‌شدهٔ DB (کامیت می‌شود)
sub_links/        # ساب‌های دائمی
```

## ⚠️ محدودیت‌ها / قدم بعدی
- هر ران اکشن ~۵.۵ ساعت است؛ آدرس تانل بعد از هر ران عوض می‌شود (ساب GitHub این را حل می‌کند).
- NoAds سمت سرور فقط روی SNI/دامنه کار می‌کند؛ تبلیغات داخل همان دامنهٔ ویدیو (مثل youtube DAI) فقط با ساب Smart + کلاینت قابل حذف است.
- پیشنهاد بعدی: XHTTP به جای WS (Xray هشدار deprecation می‌دهد)، Telegram alert هنگام expire.

**آخرین بروزرسانی:** 2026-10-06
