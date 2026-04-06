import os
import ssl
import aiohttp
import json
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# USERS & DEVIR
with open("users.json", "r", encoding="utf-8") as f:
    USERS = json.load(f)

with open("devir.json", "r", encoding="utf-8") as f:
    DEVIRS = json.load(f)

# PANELS
PANELS = {
    "panel1": {
        "url": os.environ.get("PANEL1_URL"),
        "username": os.environ.get("PANEL1_USER"),
        "password": os.environ.get("PANEL1_PASS")
    },
    "panel2": {
        "url": os.environ.get("PANEL2_URL"),
        "username": os.environ.get("PANEL2_USER"),
        "password": os.environ.get("PANEL2_PASS")
    }
}

# EFE GRUBU
EFE_GROUP = [
    "SKY09","SKY10","SKY27","SKY31","SKY40","SKY43",
    "SKY50","SKY53","SKY55","SKY59","SKY61","SKY62",
    "SKY93","SKY94"
]

# 🔥 CACHE
PANEL_CACHE = {}
CACHE_TTL = 600  # 10 dakika

# PANEL SESSION (CACHE’Lİ)
async def get_panel_session(panel_name):
    now = datetime.utcnow()

    if panel_name in PANEL_CACHE:
        session, csrf, created = PANEL_CACHE[panel_name]
        if (now - created).seconds < CACHE_TTL:
            return session, csrf

        # eski session kapat
        await session.close()

    panel = PANELS[panel_name]

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx))

    login_url = f"{panel['url']}/login"
    reports_url = f"{panel['url']}/reports/quickly"

    async with session.get(login_url) as r:
        text = await r.text()

    token = ""
    for line in text.splitlines():
        if 'name="_token"' in line:
            token = line.split('value="')[1].split('"')[0]
            break

    await session.post(login_url, data={
        "_token": token,
        "email": panel["username"],
        "password": panel["password"]
    })

    async with session.get(reports_url) as r:
        text = await r.text()

    csrf = ""
    for line in text.splitlines():
        if 'csrf-token' in line:
            csrf = line.split('content="')[1].split('"')[0]
            break

    PANEL_CACHE[panel_name] = (session, csrf, now)
    return session, csrf

# VERİ ÇEK
async def fetch_amount(session, panel_url, csrf, user_uuid):
    today = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d")

    try:
        async with session.post(
            f"{panel_url}/reports/quickly",
            headers={"X-CSRF-TOKEN": csrf, "Content-Type": "application/json"},
            json={"site": "", "dateone": today, "datetwo": today, "bank": "", "user": user_uuid}
        ) as r:
            data = await r.json()

        deposit = float(data.get("deposit", [0])[0] or 0)
        withdraw = float(data.get("withdraw", [0])[0] or 0)
        delivery = float(data.get("delivery", [0, 0])[1] or 0)

        return deposit - withdraw - delivery
    except:
        return 0

# /efe
async def efe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mesaj = f"📌 EFE ({len(EFE_GROUP)})\n"

    tasks = []
    keys = []

    for key in EFE_GROUP:
        key = key.strip().upper()

        if key not in USERS:
            mesaj += f"{key} ❌ Kullanıcı yok\n"
            continue

        info = USERS[key]
        session, csrf = await get_panel_session(info["panel"])

        keys.append(key)
        tasks.append(
            fetch_amount(
                session,
                PANELS[info["panel"]]["url"],
                csrf,
                info["uuid"]
            )
        )

    results = await asyncio.gather(*tasks)

    toplam = 0

    for key, result in zip(keys, results):
        total = result + float(DEVIRS.get(key, 0))
        toplam += total

        total_str = f"{int(total):,}".replace(",", ".") + " TL"
        mesaj += f"{key} {total_str}\n"

    toplam_str = f"{int(toplam):,}".replace(",", ".") + " TL"
    mesaj += f"Toplam: {toplam_str}"

    await update.message.reply_text(mesaj)

# BOT
if __name__ == "__main__":
    BOT_TOKEN = os.environ.get("BOT_TOKEN")

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN yok!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("efe", efe))

    print("⚡ Ultra hızlı bot çalışıyor...")
    app.run_polling()
