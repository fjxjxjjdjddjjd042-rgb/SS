"""i18n for the Telegram bot. fa is the primary language; en/ru/ar/tr fall back to en, then fa."""
from .. import settings

LANG_NAMES = {"fa": "🇮🇷 فارسی", "en": "🇬🇧 English", "ru": "🇷🇺 Русский", "ar": "🇸🇦 العربية", "tr": "🇹🇷 Türkçe"}

S = {
    "fa": {
        # ---- reply keyboard
        "kb.buy": "🛒 خرید کانفیگ", "kb.services": "📦 سرویس‌های من", "kb.wallet": "👛 کیف پول", "kb.coins": "🪙 سکه و زیرمجموعه",
        "kb.support": "💬 پشتیبانی", "kb.lang": "🌐 زبان", "kb.help": "📖 راهنما", "kb.admin": "🛠 پنل مدیریت",
        "kb.cancel": "❌ انصراف", "kb.back": "🔙 بازگشت", "kb.end_support": "🔚 پایان گفتگو",
        # ---- commands
        "cmd.start": "شروع / منوی اصلی", "cmd.buy": "خرید کانفیگ", "cmd.services": "سرویس‌های من", "cmd.wallet": "کیف پول",
        "cmd.coins": "سکه و لینک زیرمجموعه", "cmd.support": "پشتیبانی", "cmd.lang": "تغییر زبان", "cmd.help": "راهنما",
        "cmd.cancel": "لغو عملیات جاری", "cmd.admin": "پنل مدیریت",
        # ---- general
        "welcome": "سلام {name} 👋\nبه <b>{bot}</b> خوش اومدی.\nاز منوی پایین یکی از گزینه‌ها رو انتخاب کن.",
        "welcome_ref": "🎉 شما با لینک دعوت وارد شدید.",
        "menu": "منوی اصلی 👇",
        "cancelled": "✅ عملیات لغو شد.",
        "nothing_to_cancel": "عملیات فعالی برای لغو نیست.",
        "banned": "⛔️ دسترسی شما به ربات مسدود شده است.",
        "choose_lang": "زبان خود را انتخاب کنید:",
        "lang_set": "✅ زبان روی فارسی تنظیم شد.",
        "help": ("📖 <b>راهنما</b>\n\n"
                 "🛒 <b>خرید کانفیگ</b> — بسته را انتخاب و با کارت‌به‌کارت، کیف پول یا سکه پرداخت کن.\n"
                 "📦 <b>سرویس‌های من</b> — لینک اشتراک، مصرف و زمان باقی‌مانده.\n"
                 "👛 <b>کیف پول</b> — شارژ برای خرید سریع.\n"
                 "🪙 <b>سکه</b> — با دعوت دوستان سکه بگیر و کانفیگ رایگان بخر.\n"
                 "💬 <b>پشتیبانی</b> — هر مشکلی داری همین‌جا بگو.\n\n"
                 "دستورات: /buy /services /wallet /coins /support /lang /cancel"),
        "invalid_number": "❌ عدد معتبر وارد کن.",
        "unknown": "متوجه نشدم. از منوی پایین استفاده کن یا /help بزن.",
        "toman": "تومان",
        "coins_unit": "سکه",
        "unlimited": "نامحدود",
        "days": "{n} روز",
        "gb": "{n} گیگ",
        # ---- buy
        "buy.title": "🛒 <b>بسته‌ها</b>\nیکی را انتخاب کن:",
        "buy.none": "فعلاً بسته‌ای برای فروش تعریف نشده.",
        "buy.plan_btn": "{title} • {vol} • {days} • {price}",
        "buy.detail": ("📦 <b>{title}</b>\n\n💾 حجم: {vol}\n⏳ مدت: {days}\n💰 قیمت: <b>{price}</b> تومان\n🪙 با سکه: <b>{coin}</b> سکه\n\n"
                       "روش پرداخت را انتخاب کن:"),
        "buy.pay_card": "💳 کارت‌به‌کارت", "buy.pay_wallet": "👛 کیف پول ({bal} تومان)", "buy.pay_coins": "🪙 سکه ({bal} سکه)",
        "buy.no_coin_price": "این بسته با سکه قابل خرید نیست.",
        "buy.wallet_low": "❌ موجودی کیف پول کافی نیست.\nموجودی: {bal} تومان — نیاز: {need} تومان",
        "buy.coins_low": "❌ سکه کافی نداری.\nسکه‌ها: {bal} — نیاز: {need}",
        "buy.charge_wallet": "👛 شارژ کیف پول",
        "buy.confirm_wallet": "پرداخت <b>{price}</b> تومان از کیف پول برای بسته <b>{title}</b>؟",
        "buy.confirm_coins": "پرداخت <b>{price}</b> سکه برای بسته <b>{title}</b>؟",
        "buy.yes": "✅ بله، پرداخت کن", "buy.no": "❌ خیر",
        "buy.done": ("✅ <b>سرویس شما فعال شد!</b>\n\n👤 نام: <code>{name}</code>\n💾 حجم: {vol}\n⏳ مدت: {days}\n\n"
                     "🔗 لینک اشتراک (کپی و در v2rayNG / Hiddify / Streisand اضافه کن):\n<code>{sub}</code>\n\n"
                     "⚡️ لینک هوشمند (Xray JSON):\n<code>{sub_json}</code>\n\n"
                     "از «📦 سرویس‌های من» همیشه در دسترسه."),
        # ---- card payment
        "card.info": ("💳 <b>پرداخت کارت‌به‌کارت</b>\n\nمبلغ: <b>{amount}</b> تومان\n\n"
                      "شماره کارت:\n<code>{card}</code>\nبه نام: <b>{holder}</b>\n\n"
                      "بعد از واریز، روی «📤 ارسال رسید» بزن و عکس یا متن رسید را بفرست."),
        "card.not_set": "⚠️ شماره کارت هنوز توسط مدیر تنظیم نشده. لطفاً بعداً تلاش کن یا به پشتیبانی پیام بده.",
        "card.send_receipt": "📤 ارسال رسید",
        "card.ask_receipt": "عکس رسید یا متن/کد پیگیری را بفرست:",
        "card.received": ("✅ رسید شما ثبت شد.\n🧾 شناسه رسید: <code>{rid}</code>\n\n"
                          "بعد از بررسی مدیر نتیجه به شما اطلاع داده می‌شود (معمولاً کمتر از ۱ ساعت)."),
        "card.approved_plan": "🎉 رسید <code>{rid}</code> تأیید شد.",
        "card.approved_wallet": "🎉 رسید <code>{rid}</code> تأیید شد و <b>{amount}</b> تومان به کیف پول شما اضافه شد.\nموجودی: <b>{bal}</b> تومان",
        "card.rejected": "❌ رسید <code>{rid}</code> رد شد.{reason}\nاگر فکر می‌کنی اشتباهی شده به پشتیبانی پیام بده.",
        "card.pending_exists": "⏳ شما یک رسید در انتظار بررسی دارید (<code>{rid}</code>). لطفاً تا بررسی آن صبر کن.",
        # ---- wallet
        "wallet.info": ("👛 <b>کیف پول</b>\n\n💰 موجودی: <b>{bal}</b> تومان\n🪙 سکه: <b>{coins}</b>\n📦 خریدها: {orders}\n\n"
                        "آخرین تراکنش‌ها:\n{ledger}"),
        "wallet.charge": "➕ شارژ کیف پول",
        "wallet.history_empty": "— هنوز تراکنشی نداری",
        "wallet.choose_amount": "مبلغ شارژ را انتخاب کن (یا دلخواه):",
        "wallet.custom": "✏️ مبلغ دلخواه",
        "wallet.ask_custom": "مبلغ را به تومان وارد کن (حداقل {min}):",
        "wallet.min": "❌ حداقل مبلغ {min} تومان است.",
        "wallet.method": "روش پرداخت برای شارژ <b>{amount}</b> تومان:",
        "ledger.wallet": "کیف پول", "ledger.coins": "سکه",
        # ---- coins / referral
        "coins.info": ("🪙 <b>سکه و زیرمجموعه</b>\n\n🪙 سکه‌های شما: <b>{coins}</b>\n👥 زیرمجموعه‌ها: <b>{refs}</b>\n"
                       "🎁 هر دعوت موفق: <b>{per}</b> سکه\n\n"
                       "🔗 لینک اختصاصی شما:\n<code>{link}</code>\n\n"
                       "لینک را برای دوستانت بفرست؛ هر کسی که برای اولین بار با آن ربات را استارت کند، سکه می‌گیری. "
                       "با سکه‌ها می‌تونی بسته بخری (🛒 خرید کانفیگ → پرداخت با سکه)."),
        "coins.new_ref": "🎉 یک زیرمجموعه جدید اضافه شد! <b>+{per}</b> سکه. مجموع سکه: <b>{coins}</b>",
        "coins.share": "📣 اشتراک‌گذاری لینک",
        # ---- services
        "svc.none": "📦 هنوز سرویسی نداری.\nاز «🛒 خرید کانفیگ» اولین سرویس‌ت رو بگیر.",
        "svc.list": "📦 <b>سرویس‌های من</b>\nیکی را انتخاب کن:",
        "svc.detail": ("📦 <b>{name}</b>  {status}\n\n📊 مصرف: {used} از {total}\n{bar} {pct}%\n⏳ باقی‌مانده: {rem}\n"
                       "📶 وضعیت: {online}\n\n🔗 لینک اشتراک:\n<code>{sub}</code>\n\n⚡️ لینک هوشمند:\n<code>{sub_json}</code>"),
        "svc.status.active": "🟢 فعال", "svc.status.expired": "🔴 منقضی", "svc.status.disabled": "⚪️ غیرفعال",
        "svc.online": "آنلاین", "svc.offline": "آفلاین",
        "svc.renew": "🔄 تمدید / خرید حجم", "svc.links": "🔗 همه لینک‌ها", "svc.refresh": "♻️ بروزرسانی",
        "svc.links_text": ("🔗 <b>لینک‌های {name}</b>\n\n📱 ساب ساده (v2rayNG/Hiddify):\n<code>{sub}</code>\n\n"
                           "⚡️ ساب هوشمند Xray:\n<code>{sub_json}</code>\n\n📦 sing-box:\n<code>{sub_sb}</code>\n\n"
                           "🧩 کانفیگ تکی:\n<code>{config}</code>"),
        "svc.alert80": "⚠️ <b>{name}</b>: {pct}% حجم بسته‌ات مصرف شده ({used} از {total}).\nبرای جلوگیری از قطعی، از «🛒 خرید کانفیگ» تمدید کن.",
        "svc.alert_expired": "🔴 سرویس <b>{name}</b> به پایان رسید ({why}). برای ادامه، بسته جدید بگیر.",
        "svc.why_volume": "اتمام حجم", "svc.why_time": "اتمام زمان",
        # ---- support
        "sup.start": "💬 <b>پشتیبانی</b>\nمشکل یا سوالت رو بنویس؛ همین‌جا جواب می‌دیم.\nبرای خروج «🔚 پایان گفتگو» رو بزن.",
        "sup.ended": "گفتگو بسته شد. هر وقت خواستی دوباره پیام بده 🌹",
        "sup.unavailable": "پشتیبانی موقتاً در دسترس نیست. لطفاً کمی بعد دوباره تلاش کن.",
        "sup.timeout": "⌛️ گفتگوی پشتیبانی به دلیل عدم فعالیت بسته شد.",
        "sup.busy": "یه لحظه… پیام قبلی‌ت در حال بررسیه.",
    },
    "en": {
        "kb.buy": "🛒 Buy config", "kb.services": "📦 My services", "kb.wallet": "👛 Wallet", "kb.coins": "🪙 Coins & referral",
        "kb.support": "💬 Support", "kb.lang": "🌐 Language", "kb.help": "📖 Help", "kb.admin": "🛠 Admin panel",
        "kb.cancel": "❌ Cancel", "kb.back": "🔙 Back", "kb.end_support": "🔚 End chat",
        "cmd.start": "Start / main menu", "cmd.buy": "Buy config", "cmd.services": "My services", "cmd.wallet": "Wallet",
        "cmd.coins": "Coins & referral link", "cmd.support": "Support", "cmd.lang": "Change language", "cmd.help": "Help",
        "cmd.cancel": "Cancel current action", "cmd.admin": "Admin panel",
        "welcome": "Hi {name} 👋\nWelcome to <b>{bot}</b>.\nPick an option from the menu below.",
        "welcome_ref": "🎉 You joined via an invite link.",
        "menu": "Main menu 👇", "cancelled": "✅ Cancelled.", "nothing_to_cancel": "Nothing to cancel.",
        "banned": "⛔️ You are blocked from using this bot.", "choose_lang": "Choose your language:",
        "lang_set": "✅ Language set to English.",
        "help": ("📖 <b>Help</b>\n\n🛒 <b>Buy config</b> — pick a plan, pay by card transfer, wallet or coins.\n"
                 "📦 <b>My services</b> — subscription links, usage and remaining time.\n👛 <b>Wallet</b> — top up for quick purchases.\n"
                 "🪙 <b>Coins</b> — invite friends, earn coins, get free configs.\n💬 <b>Support</b> — tell us about any issue.\n\n"
                 "Commands: /buy /services /wallet /coins /support /lang /cancel"),
        "invalid_number": "❌ Enter a valid number.", "unknown": "Didn't get that. Use the menu below or /help.",
        "toman": "Toman", "coins_unit": "coins", "unlimited": "Unlimited", "days": "{n} days", "gb": "{n} GB",
        "buy.title": "🛒 <b>Plans</b>\nChoose one:", "buy.none": "No plans available yet.",
        "buy.plan_btn": "{title} • {vol} • {days} • {price}",
        "buy.detail": "📦 <b>{title}</b>\n\n💾 Volume: {vol}\n⏳ Duration: {days}\n💰 Price: <b>{price}</b> Toman\n🪙 Coins: <b>{coin}</b>\n\nChoose payment method:",
        "buy.pay_card": "💳 Card transfer", "buy.pay_wallet": "👛 Wallet ({bal} T)", "buy.pay_coins": "🪙 Coins ({bal})",
        "buy.no_coin_price": "This plan can't be bought with coins.",
        "buy.wallet_low": "❌ Insufficient wallet balance.\nBalance: {bal} — Needed: {need}",
        "buy.coins_low": "❌ Not enough coins.\nCoins: {bal} — Needed: {need}", "buy.charge_wallet": "👛 Top up wallet",
        "buy.confirm_wallet": "Pay <b>{price}</b> Toman from wallet for <b>{title}</b>?",
        "buy.confirm_coins": "Pay <b>{price}</b> coins for <b>{title}</b>?", "buy.yes": "✅ Yes, pay", "buy.no": "❌ No",
        "buy.done": ("✅ <b>Your service is active!</b>\n\n👤 Name: <code>{name}</code>\n💾 Volume: {vol}\n⏳ Duration: {days}\n\n"
                     "🔗 Subscription link (add to v2rayNG / Hiddify / Streisand):\n<code>{sub}</code>\n\n"
                     "⚡️ Smart link (Xray JSON):\n<code>{sub_json}</code>\n\nAlways available in «📦 My services»."),
        "card.info": ("💳 <b>Card transfer</b>\n\nAmount: <b>{amount}</b> Toman\n\nCard number:\n<code>{card}</code>\nHolder: <b>{holder}</b>\n\n"
                      "After paying, tap «📤 Send receipt» and send a photo or the tracking text."),
        "card.not_set": "⚠️ Card number isn't configured yet. Try later or contact support.",
        "card.send_receipt": "📤 Send receipt", "card.ask_receipt": "Send the receipt photo or tracking code:",
        "card.received": "✅ Receipt saved.\n🧾 Receipt ID: <code>{rid}</code>\n\nYou'll be notified after review (usually < 1 hour).",
        "card.approved_plan": "🎉 Receipt <code>{rid}</code> approved.",
        "card.approved_wallet": "🎉 Receipt <code>{rid}</code> approved; <b>{amount}</b> Toman added.\nBalance: <b>{bal}</b> Toman",
        "card.rejected": "❌ Receipt <code>{rid}</code> rejected.{reason}\nContact support if you think this is a mistake.",
        "card.pending_exists": "⏳ You already have a pending receipt (<code>{rid}</code>). Please wait for review.",
        "wallet.info": "👛 <b>Wallet</b>\n\n💰 Balance: <b>{bal}</b> Toman\n🪙 Coins: <b>{coins}</b>\n📦 Orders: {orders}\n\nRecent transactions:\n{ledger}",
        "wallet.charge": "➕ Top up", "wallet.history_empty": "— no transactions yet",
        "wallet.choose_amount": "Choose amount (or custom):", "wallet.custom": "✏️ Custom amount",
        "wallet.ask_custom": "Enter amount in Toman (min {min}):", "wallet.min": "❌ Minimum is {min} Toman.",
        "wallet.method": "Payment method for <b>{amount}</b> Toman:", "ledger.wallet": "wallet", "ledger.coins": "coins",
        "coins.info": ("🪙 <b>Coins & referral</b>\n\n🪙 Your coins: <b>{coins}</b>\n👥 Referrals: <b>{refs}</b>\n🎁 Per invite: <b>{per}</b> coins\n\n"
                       "🔗 Your link:\n<code>{link}</code>\n\nShare it; whenever someone starts the bot for the first time with it, you earn coins. "
                       "Spend coins in 🛒 Buy config → pay with coins."),
        "coins.new_ref": "🎉 New referral! <b>+{per}</b> coins. Total: <b>{coins}</b>", "coins.share": "📣 Share link",
        "svc.none": "📦 You have no services yet.\nGet your first one from «🛒 Buy config».", "svc.list": "📦 <b>My services</b>\nChoose one:",
        "svc.detail": "📦 <b>{name}</b>  {status}\n\n📊 Used: {used} of {total}\n{bar} {pct}%\n⏳ Remaining: {rem}\n📶 {online}\n\n🔗 Subscription:\n<code>{sub}</code>\n\n⚡️ Smart link:\n<code>{sub_json}</code>",
        "svc.status.active": "🟢 Active", "svc.status.expired": "🔴 Expired", "svc.status.disabled": "⚪️ Disabled",
        "svc.online": "Online", "svc.offline": "Offline", "svc.renew": "🔄 Renew / add volume", "svc.links": "🔗 All links", "svc.refresh": "♻️ Refresh",
        "svc.links_text": "🔗 <b>Links for {name}</b>\n\n📱 Simple sub:\n<code>{sub}</code>\n\n⚡️ Smart Xray sub:\n<code>{sub_json}</code>\n\n📦 sing-box:\n<code>{sub_sb}</code>\n\n🧩 Single config:\n<code>{config}</code>",
        "svc.alert80": "⚠️ <b>{name}</b>: {pct}% of your volume is used ({used} of {total}).\nRenew from «🛒 Buy config» to avoid interruption.",
        "svc.alert_expired": "🔴 Service <b>{name}</b> ended ({why}). Get a new plan to continue.",
        "svc.why_volume": "volume exhausted", "svc.why_time": "time expired",
        "sup.start": "💬 <b>Support</b>\nDescribe your issue; we'll answer right here.\nTap «🔚 End chat» to leave.",
        "sup.ended": "Chat closed. Message us anytime 🌹", "sup.unavailable": "Support is temporarily unavailable. Please try again later.",
        "sup.timeout": "⌛️ Support chat closed due to inactivity.", "sup.busy": "One moment… still working on your previous message.",
    },
    "ru": {
        "kb.buy": "🛒 Купить конфиг", "kb.services": "📦 Мои сервисы", "kb.wallet": "👛 Кошелёк", "kb.coins": "🪙 Монеты и рефералы",
        "kb.support": "💬 Поддержка", "kb.lang": "🌐 Язык", "kb.help": "📖 Помощь", "kb.admin": "🛠 Админ-панель",
        "kb.cancel": "❌ Отмена", "kb.back": "🔙 Назад", "kb.end_support": "🔚 Завершить чат",
        "cmd.start": "Старт / главное меню", "cmd.buy": "Купить конфиг", "cmd.services": "Мои сервисы", "cmd.wallet": "Кошелёк",
        "cmd.coins": "Монеты и реферальная ссылка", "cmd.support": "Поддержка", "cmd.lang": "Сменить язык", "cmd.help": "Помощь",
        "cmd.cancel": "Отменить действие", "cmd.admin": "Админ-панель",
        "welcome": "Привет, {name} 👋\nДобро пожаловать в <b>{bot}</b>.\nВыберите пункт меню ниже.",
        "welcome_ref": "🎉 Вы пришли по пригласительной ссылке.", "menu": "Главное меню 👇", "cancelled": "✅ Отменено.",
        "nothing_to_cancel": "Нечего отменять.", "banned": "⛔️ Доступ к боту заблокирован.", "choose_lang": "Выберите язык:",
        "lang_set": "✅ Язык: русский.",
        "help": ("📖 <b>Помощь</b>\n\n🛒 <b>Купить конфиг</b> — выберите тариф, оплатите переводом, кошельком или монетами.\n"
                 "📦 <b>Мои сервисы</b> — ссылки подписки, трафик и остаток времени.\n👛 <b>Кошелёк</b> — пополните для быстрых покупок.\n"
                 "🪙 <b>Монеты</b> — приглашайте друзей и получайте бесплатные конфиги.\n💬 <b>Поддержка</b> — опишите любую проблему.\n\n"
                 "Команды: /buy /services /wallet /coins /support /lang /cancel"),
        "invalid_number": "❌ Введите корректное число.", "unknown": "Не понял. Используйте меню или /help.",
        "toman": "туманов", "coins_unit": "монет", "unlimited": "Безлимит", "days": "{n} дн.", "gb": "{n} ГБ",
        "buy.title": "🛒 <b>Тарифы</b>\nВыберите:", "buy.none": "Тарифов пока нет.", "buy.plan_btn": "{title} • {vol} • {days} • {price}",
        "buy.detail": "📦 <b>{title}</b>\n\n💾 Трафик: {vol}\n⏳ Срок: {days}\n💰 Цена: <b>{price}</b> туманов\n🪙 Монетами: <b>{coin}</b>\n\nСпособ оплаты:",
        "buy.pay_card": "💳 Перевод на карту", "buy.pay_wallet": "👛 Кошелёк ({bal})", "buy.pay_coins": "🪙 Монеты ({bal})",
        "buy.no_coin_price": "Этот тариф нельзя купить за монеты.",
        "buy.wallet_low": "❌ Недостаточно средств.\nБаланс: {bal} — Нужно: {need}", "buy.coins_low": "❌ Недостаточно монет.\nМонет: {bal} — Нужно: {need}",
        "buy.charge_wallet": "👛 Пополнить кошелёк", "buy.confirm_wallet": "Оплатить <b>{price}</b> туманов из кошелька за <b>{title}</b>?",
        "buy.confirm_coins": "Оплатить <b>{price}</b> монет за <b>{title}</b>?", "buy.yes": "✅ Да, оплатить", "buy.no": "❌ Нет",
        "buy.done": "✅ <b>Сервис активирован!</b>\n\n👤 Имя: <code>{name}</code>\n💾 Трафик: {vol}\n⏳ Срок: {days}\n\n🔗 Ссылка подписки:\n<code>{sub}</code>\n\n⚡️ Умная ссылка (Xray JSON):\n<code>{sub_json}</code>\n\nВсегда доступно в «📦 Мои сервисы».",
        "card.info": "💳 <b>Перевод на карту</b>\n\nСумма: <b>{amount}</b> туманов\n\nНомер карты:\n<code>{card}</code>\nПолучатель: <b>{holder}</b>\n\nПосле оплаты нажмите «📤 Отправить чек».",
        "card.not_set": "⚠️ Номер карты ещё не настроен. Попробуйте позже или напишите в поддержку.",
        "card.send_receipt": "📤 Отправить чек", "card.ask_receipt": "Отправьте фото чека или код операции:",
        "card.received": "✅ Чек сохранён.\n🧾 ID чека: <code>{rid}</code>\n\nМы уведомим вас после проверки.",
        "card.approved_plan": "🎉 Чек <code>{rid}</code> подтверждён.",
        "card.approved_wallet": "🎉 Чек <code>{rid}</code> подтверждён; зачислено <b>{amount}</b>.\nБаланс: <b>{bal}</b>",
        "card.rejected": "❌ Чек <code>{rid}</code> отклонён.{reason}\nЕсли это ошибка — напишите в поддержку.",
        "card.pending_exists": "⏳ У вас уже есть чек на проверке (<code>{rid}</code>).",
        "wallet.info": "👛 <b>Кошелёк</b>\n\n💰 Баланс: <b>{bal}</b>\n🪙 Монеты: <b>{coins}</b>\n📦 Заказы: {orders}\n\nПоследние операции:\n{ledger}",
        "wallet.charge": "➕ Пополнить", "wallet.history_empty": "— операций пока нет", "wallet.choose_amount": "Выберите сумму (или свою):",
        "wallet.custom": "✏️ Своя сумма", "wallet.ask_custom": "Введите сумму (мин. {min}):", "wallet.min": "❌ Минимум {min}.",
        "wallet.method": "Способ оплаты для <b>{amount}</b>:", "ledger.wallet": "кошелёк", "ledger.coins": "монеты",
        "coins.info": "🪙 <b>Монеты и рефералы</b>\n\n🪙 Монет: <b>{coins}</b>\n👥 Рефералов: <b>{refs}</b>\n🎁 За приглашение: <b>{per}</b>\n\n🔗 Ваша ссылка:\n<code>{link}</code>\n\nДелитесь ссылкой — за каждого нового пользователя получаете монеты.",
        "coins.new_ref": "🎉 Новый реферал! <b>+{per}</b> монет. Всего: <b>{coins}</b>", "coins.share": "📣 Поделиться",
        "svc.none": "📦 У вас пока нет сервисов.", "svc.list": "📦 <b>Мои сервисы</b>\nВыберите:",
        "svc.detail": "📦 <b>{name}</b>  {status}\n\n📊 Использовано: {used} из {total}\n{bar} {pct}%\n⏳ Осталось: {rem}\n📶 {online}\n\n🔗 Подписка:\n<code>{sub}</code>\n\n⚡️ Умная ссылка:\n<code>{sub_json}</code>",
        "svc.status.active": "🟢 Активен", "svc.status.expired": "🔴 Истёк", "svc.status.disabled": "⚪️ Отключён",
        "svc.online": "Онлайн", "svc.offline": "Оффлайн", "svc.renew": "🔄 Продлить", "svc.links": "🔗 Все ссылки", "svc.refresh": "♻️ Обновить",
        "svc.links_text": "🔗 <b>Ссылки {name}</b>\n\n📱 Подписка:\n<code>{sub}</code>\n\n⚡️ Xray JSON:\n<code>{sub_json}</code>\n\n📦 sing-box:\n<code>{sub_sb}</code>\n\n🧩 Конфиг:\n<code>{config}</code>",
        "svc.alert80": "⚠️ <b>{name}</b>: использовано {pct}% трафика ({used} из {total}). Продлите заранее.",
        "svc.alert_expired": "🔴 Сервис <b>{name}</b> завершён ({why}).", "svc.why_volume": "трафик исчерпан", "svc.why_time": "срок истёк",
        "sup.start": "💬 <b>Поддержка</b>\nОпишите проблему — ответим здесь.\n«🔚 Завершить чат» для выхода.",
        "sup.ended": "Чат закрыт. Пишите в любое время 🌹", "sup.unavailable": "Поддержка временно недоступна.",
        "sup.timeout": "⌛️ Чат закрыт из-за неактивности.", "sup.busy": "Секунду… обрабатываю предыдущее сообщение.",
    },
    "ar": {
        "kb.buy": "🛒 شراء الاشتراك", "kb.services": "📦 خدماتي", "kb.wallet": "👛 المحفظة", "kb.coins": "🪙 العملات والإحالة",
        "kb.support": "💬 الدعم", "kb.lang": "🌐 اللغة", "kb.help": "📖 المساعدة", "kb.admin": "🛠 لوحة الإدارة",
        "kb.cancel": "❌ إلغاء", "kb.back": "🔙 رجوع", "kb.end_support": "🔚 إنهاء المحادثة",
        "cmd.start": "البداية / القائمة", "cmd.buy": "شراء الاشتراك", "cmd.services": "خدماتي", "cmd.wallet": "المحفظة",
        "cmd.coins": "العملات ورابط الإحالة", "cmd.support": "الدعم", "cmd.lang": "تغيير اللغة", "cmd.help": "المساعدة",
        "cmd.cancel": "إلغاء العملية", "cmd.admin": "لوحة الإدارة",
        "welcome": "مرحباً {name} 👋\nأهلاً بك في <b>{bot}</b>.\nاختر من القائمة أدناه.",
        "welcome_ref": "🎉 انضممت عبر رابط دعوة.", "menu": "القائمة الرئيسية 👇", "cancelled": "✅ تم الإلغاء.",
        "nothing_to_cancel": "لا يوجد ما يُلغى.", "banned": "⛔️ تم حظرك من استخدام البوت.", "choose_lang": "اختر لغتك:",
        "lang_set": "✅ تم ضبط اللغة: العربية.",
        "help": ("📖 <b>المساعدة</b>\n\n🛒 <b>شراء الاشتراك</b> — اختر باقة وادفع بالتحويل أو المحفظة أو العملات.\n"
                 "📦 <b>خدماتي</b> — روابط الاشتراك والاستهلاك والوقت المتبقي.\n👛 <b>المحفظة</b> — اشحن للشراء السريع.\n"
                 "🪙 <b>العملات</b> — ادعُ أصدقاءك واحصل على اشتراكات مجانية.\n💬 <b>الدعم</b> — أخبرنا بأي مشكلة.\n\n"
                 "الأوامر: /buy /services /wallet /coins /support /lang /cancel"),
        "invalid_number": "❌ أدخل رقماً صحيحاً.", "unknown": "لم أفهم. استخدم القائمة أو /help.",
        "toman": "تومان", "coins_unit": "عملة", "unlimited": "غير محدود", "days": "{n} يوم", "gb": "{n} جيجا",
        "buy.title": "🛒 <b>الباقات</b>\nاختر واحدة:", "buy.none": "لا توجد باقات حالياً.", "buy.plan_btn": "{title} • {vol} • {days} • {price}",
        "buy.detail": "📦 <b>{title}</b>\n\n💾 الحجم: {vol}\n⏳ المدة: {days}\n💰 السعر: <b>{price}</b> تومان\n🪙 بالعملات: <b>{coin}</b>\n\nاختر طريقة الدفع:",
        "buy.pay_card": "💳 تحويل بنكي", "buy.pay_wallet": "👛 المحفظة ({bal})", "buy.pay_coins": "🪙 العملات ({bal})",
        "buy.no_coin_price": "لا يمكن شراء هذه الباقة بالعملات.",
        "buy.wallet_low": "❌ رصيد المحفظة غير كافٍ.\nالرصيد: {bal} — المطلوب: {need}", "buy.coins_low": "❌ العملات غير كافية.\nلديك: {bal} — المطلوب: {need}",
        "buy.charge_wallet": "👛 شحن المحفظة", "buy.confirm_wallet": "دفع <b>{price}</b> تومان من المحفظة لباقة <b>{title}</b>؟",
        "buy.confirm_coins": "دفع <b>{price}</b> عملة لباقة <b>{title}</b>؟", "buy.yes": "✅ نعم، ادفع", "buy.no": "❌ لا",
        "buy.done": "✅ <b>تم تفعيل خدمتك!</b>\n\n👤 الاسم: <code>{name}</code>\n💾 الحجم: {vol}\n⏳ المدة: {days}\n\n🔗 رابط الاشتراك:\n<code>{sub}</code>\n\n⚡️ الرابط الذكي (Xray JSON):\n<code>{sub_json}</code>\n\nمتاح دائماً في «📦 خدماتي».",
        "card.info": "💳 <b>تحويل بنكي</b>\n\nالمبلغ: <b>{amount}</b> تومان\n\nرقم البطاقة:\n<code>{card}</code>\nباسم: <b>{holder}</b>\n\nبعد الدفع اضغط «📤 إرسال الإيصال».",
        "card.not_set": "⚠️ لم يتم ضبط رقم البطاقة بعد. حاول لاحقاً أو تواصل مع الدعم.",
        "card.send_receipt": "📤 إرسال الإيصال", "card.ask_receipt": "أرسل صورة الإيصال أو رقم العملية:",
        "card.received": "✅ تم حفظ الإيصال.\n🧾 المعرف: <code>{rid}</code>\n\nسنُعلمك بعد المراجعة.",
        "card.approved_plan": "🎉 تم قبول الإيصال <code>{rid}</code>.",
        "card.approved_wallet": "🎉 تم قبول الإيصال <code>{rid}</code> وإضافة <b>{amount}</b>.\nالرصيد: <b>{bal}</b>",
        "card.rejected": "❌ تم رفض الإيصال <code>{rid}</code>.{reason}\nتواصل مع الدعم إن كان هناك خطأ.",
        "card.pending_exists": "⏳ لديك إيصال قيد المراجعة (<code>{rid}</code>).",
        "wallet.info": "👛 <b>المحفظة</b>\n\n💰 الرصيد: <b>{bal}</b> تومان\n🪙 العملات: <b>{coins}</b>\n📦 الطلبات: {orders}\n\nآخر العمليات:\n{ledger}",
        "wallet.charge": "➕ شحن", "wallet.history_empty": "— لا عمليات بعد", "wallet.choose_amount": "اختر المبلغ (أو مخصص):",
        "wallet.custom": "✏️ مبلغ مخصص", "wallet.ask_custom": "أدخل المبلغ بالتومان (الحد الأدنى {min}):", "wallet.min": "❌ الحد الأدنى {min}.",
        "wallet.method": "طريقة الدفع لمبلغ <b>{amount}</b>:", "ledger.wallet": "المحفظة", "ledger.coins": "العملات",
        "coins.info": "🪙 <b>العملات والإحالة</b>\n\n🪙 عملاتك: <b>{coins}</b>\n👥 الإحالات: <b>{refs}</b>\n🎁 لكل دعوة: <b>{per}</b>\n\n🔗 رابطك:\n<code>{link}</code>\n\nشارك الرابط؛ تحصل على عملات عن كل مستخدم جديد.",
        "coins.new_ref": "🎉 إحالة جديدة! <b>+{per}</b> عملة. المجموع: <b>{coins}</b>", "coins.share": "📣 مشاركة الرابط",
        "svc.none": "📦 لا توجد خدمات بعد.", "svc.list": "📦 <b>خدماتي</b>\nاختر:",
        "svc.detail": "📦 <b>{name}</b>  {status}\n\n📊 المستهلك: {used} من {total}\n{bar} {pct}%\n⏳ المتبقي: {rem}\n📶 {online}\n\n🔗 الاشتراك:\n<code>{sub}</code>\n\n⚡️ الرابط الذكي:\n<code>{sub_json}</code>",
        "svc.status.active": "🟢 نشط", "svc.status.expired": "🔴 منتهي", "svc.status.disabled": "⚪️ معطّل",
        "svc.online": "متصل", "svc.offline": "غير متصل", "svc.renew": "🔄 تجديد", "svc.links": "🔗 كل الروابط", "svc.refresh": "♻️ تحديث",
        "svc.links_text": "🔗 <b>روابط {name}</b>\n\n📱 الاشتراك:\n<code>{sub}</code>\n\n⚡️ Xray JSON:\n<code>{sub_json}</code>\n\n📦 sing-box:\n<code>{sub_sb}</code>\n\n🧩 إعداد مفرد:\n<code>{config}</code>",
        "svc.alert80": "⚠️ <b>{name}</b>: استُهلك {pct}% من الحجم ({used} من {total}). جدّد مبكراً.",
        "svc.alert_expired": "🔴 انتهت خدمة <b>{name}</b> ({why}).", "svc.why_volume": "نفاد الحجم", "svc.why_time": "انتهاء المدة",
        "sup.start": "💬 <b>الدعم</b>\nاكتب مشكلتك وسنجيب هنا.\n«🔚 إنهاء المحادثة» للخروج.",
        "sup.ended": "أُغلقت المحادثة. راسلنا في أي وقت 🌹", "sup.unavailable": "الدعم غير متاح مؤقتاً.",
        "sup.timeout": "⌛️ أُغلقت المحادثة بسبب عدم النشاط.", "sup.busy": "لحظة… ما زلت أعالج رسالتك السابقة.",
    },
    "tr": {
        "kb.buy": "🛒 Config satın al", "kb.services": "📦 Hizmetlerim", "kb.wallet": "👛 Cüzdan", "kb.coins": "🪙 Coin & davet",
        "kb.support": "💬 Destek", "kb.lang": "🌐 Dil", "kb.help": "📖 Yardım", "kb.admin": "🛠 Yönetim paneli",
        "kb.cancel": "❌ İptal", "kb.back": "🔙 Geri", "kb.end_support": "🔚 Sohbeti bitir",
        "cmd.start": "Başlat / ana menü", "cmd.buy": "Config satın al", "cmd.services": "Hizmetlerim", "cmd.wallet": "Cüzdan",
        "cmd.coins": "Coin ve davet linki", "cmd.support": "Destek", "cmd.lang": "Dili değiştir", "cmd.help": "Yardım",
        "cmd.cancel": "İşlemi iptal et", "cmd.admin": "Yönetim paneli",
        "welcome": "Merhaba {name} 👋\n<b>{bot}</b>'a hoş geldin.\nAşağıdaki menüden seç.",
        "welcome_ref": "🎉 Davet linkiyle katıldın.", "menu": "Ana menü 👇", "cancelled": "✅ İptal edildi.",
        "nothing_to_cancel": "İptal edilecek işlem yok.", "banned": "⛔️ Botu kullanmanız engellendi.", "choose_lang": "Dilini seç:",
        "lang_set": "✅ Dil: Türkçe.",
        "help": ("📖 <b>Yardım</b>\n\n🛒 <b>Config satın al</b> — paket seç; havale, cüzdan veya coin ile öde.\n"
                 "📦 <b>Hizmetlerim</b> — abonelik linkleri, kullanım ve kalan süre.\n👛 <b>Cüzdan</b> — hızlı alışveriş için yükle.\n"
                 "🪙 <b>Coin</b> — arkadaşlarını davet et, ücretsiz config kazan.\n💬 <b>Destek</b> — her sorunu buraya yaz.\n\n"
                 "Komutlar: /buy /services /wallet /coins /support /lang /cancel"),
        "invalid_number": "❌ Geçerli bir sayı gir.", "unknown": "Anlamadım. Menüyü kullan veya /help yaz.",
        "toman": "Toman", "coins_unit": "coin", "unlimited": "Sınırsız", "days": "{n} gün", "gb": "{n} GB",
        "buy.title": "🛒 <b>Paketler</b>\nBirini seç:", "buy.none": "Henüz paket yok.", "buy.plan_btn": "{title} • {vol} • {days} • {price}",
        "buy.detail": "📦 <b>{title}</b>\n\n💾 Hacim: {vol}\n⏳ Süre: {days}\n💰 Fiyat: <b>{price}</b> Toman\n🪙 Coin: <b>{coin}</b>\n\nÖdeme yöntemi:",
        "buy.pay_card": "💳 Havale", "buy.pay_wallet": "👛 Cüzdan ({bal})", "buy.pay_coins": "🪙 Coin ({bal})",
        "buy.no_coin_price": "Bu paket coin ile alınamaz.",
        "buy.wallet_low": "❌ Cüzdan bakiyesi yetersiz.\nBakiye: {bal} — Gerekli: {need}", "buy.coins_low": "❌ Yeterli coin yok.\nCoin: {bal} — Gerekli: {need}",
        "buy.charge_wallet": "👛 Cüzdan yükle", "buy.confirm_wallet": "<b>{title}</b> için cüzdandan <b>{price}</b> Toman ödensin mi?",
        "buy.confirm_coins": "<b>{title}</b> için <b>{price}</b> coin ödensin mi?", "buy.yes": "✅ Evet, öde", "buy.no": "❌ Hayır",
        "buy.done": "✅ <b>Hizmetin aktif!</b>\n\n👤 Ad: <code>{name}</code>\n💾 Hacim: {vol}\n⏳ Süre: {days}\n\n🔗 Abonelik linki:\n<code>{sub}</code>\n\n⚡️ Akıllı link (Xray JSON):\n<code>{sub_json}</code>\n\n«📦 Hizmetlerim»den her zaman ulaşabilirsin.",
        "card.info": "💳 <b>Havale</b>\n\nTutar: <b>{amount}</b> Toman\n\nKart numarası:\n<code>{card}</code>\nAd: <b>{holder}</b>\n\nÖdemeden sonra «📤 Dekont gönder»e bas.",
        "card.not_set": "⚠️ Kart numarası henüz ayarlanmadı. Daha sonra dene veya desteğe yaz.",
        "card.send_receipt": "📤 Dekont gönder", "card.ask_receipt": "Dekont fotoğrafını veya işlem kodunu gönder:",
        "card.received": "✅ Dekont kaydedildi.\n🧾 ID: <code>{rid}</code>\n\nİnceleme sonrası bilgilendirileceksin.",
        "card.approved_plan": "🎉 Dekont <code>{rid}</code> onaylandı.",
        "card.approved_wallet": "🎉 Dekont <code>{rid}</code> onaylandı; <b>{amount}</b> eklendi.\nBakiye: <b>{bal}</b>",
        "card.rejected": "❌ Dekont <code>{rid}</code> reddedildi.{reason}\nHata olduğunu düşünüyorsan desteğe yaz.",
        "card.pending_exists": "⏳ Zaten bekleyen bir dekontun var (<code>{rid}</code>).",
        "wallet.info": "👛 <b>Cüzdan</b>\n\n💰 Bakiye: <b>{bal}</b> Toman\n🪙 Coin: <b>{coins}</b>\n📦 Siparişler: {orders}\n\nSon işlemler:\n{ledger}",
        "wallet.charge": "➕ Yükle", "wallet.history_empty": "— henüz işlem yok", "wallet.choose_amount": "Tutar seç (veya özel):",
        "wallet.custom": "✏️ Özel tutar", "wallet.ask_custom": "Tutarı Toman olarak gir (min {min}):", "wallet.min": "❌ Minimum {min}.",
        "wallet.method": "<b>{amount}</b> için ödeme yöntemi:", "ledger.wallet": "cüzdan", "ledger.coins": "coin",
        "coins.info": "🪙 <b>Coin & davet</b>\n\n🪙 Coin: <b>{coins}</b>\n👥 Davetler: <b>{refs}</b>\n🎁 Davet başına: <b>{per}</b>\n\n🔗 Linkin:\n<code>{link}</code>\n\nLinki paylaş; her yeni kullanıcı için coin kazan.",
        "coins.new_ref": "🎉 Yeni davet! <b>+{per}</b> coin. Toplam: <b>{coins}</b>", "coins.share": "📣 Linki paylaş",
        "svc.none": "📦 Henüz hizmetin yok.", "svc.list": "📦 <b>Hizmetlerim</b>\nSeç:",
        "svc.detail": "📦 <b>{name}</b>  {status}\n\n📊 Kullanım: {used} / {total}\n{bar} {pct}%\n⏳ Kalan: {rem}\n📶 {online}\n\n🔗 Abonelik:\n<code>{sub}</code>\n\n⚡️ Akıllı link:\n<code>{sub_json}</code>",
        "svc.status.active": "🟢 Aktif", "svc.status.expired": "🔴 Süresi doldu", "svc.status.disabled": "⚪️ Devre dışı",
        "svc.online": "Çevrimiçi", "svc.offline": "Çevrimdışı", "svc.renew": "🔄 Yenile", "svc.links": "🔗 Tüm linkler", "svc.refresh": "♻️ Yenile",
        "svc.links_text": "🔗 <b>{name} linkleri</b>\n\n📱 Abonelik:\n<code>{sub}</code>\n\n⚡️ Xray JSON:\n<code>{sub_json}</code>\n\n📦 sing-box:\n<code>{sub_sb}</code>\n\n🧩 Tek config:\n<code>{config}</code>",
        "svc.alert80": "⚠️ <b>{name}</b>: hacmin %{pct}'i kullanıldı ({used} / {total}). Erken yenile.",
        "svc.alert_expired": "🔴 <b>{name}</b> hizmeti bitti ({why}).", "svc.why_volume": "hacim bitti", "svc.why_time": "süre doldu",
        "sup.start": "💬 <b>Destek</b>\nSorununu yaz; burada cevaplayacağız.\nÇıkmak için «🔚 Sohbeti bitir».",
        "sup.ended": "Sohbet kapatıldı. İstediğin zaman yaz 🌹", "sup.unavailable": "Destek geçici olarak kullanılamıyor.",
        "sup.timeout": "⌛️ Sohbet hareketsizlik nedeniyle kapatıldı.", "sup.busy": "Bir saniye… önceki mesajın işleniyor.",
    },
}


def norm_lang(code):
    code = (code or "").lower().split("-")[0]
    return code if code in settings.SUPPORTED_LANGS else settings.DEFAULT_LANG


def t(lang, key, **kw):
    lang = norm_lang(lang)
    s = S.get(lang, {}).get(key) or S["en"].get(key) or S["fa"].get(key) or key
    try:
        return s.format(**kw) if kw else s
    except Exception:
        return s


def fmt_num(n):
    """1234567 -> 1,234,567"""
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


def kb_labels(lang):
    """All reply-keyboard labels in every language -> canonical action (so a stale keyboard still works)."""
    out = {}
    for lg in S:
        for key in ("kb.buy", "kb.services", "kb.wallet", "kb.coins", "kb.support", "kb.lang", "kb.help", "kb.admin",
                    "kb.cancel", "kb.back", "kb.end_support"):
            out[S[lg][key]] = key
    return out


KB_ACTIONS = kb_labels(None)
