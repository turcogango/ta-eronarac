import os
import ssl
import aiohttp
import json
import asyncio
import re
import unicodedata
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes, ApplicationBuilder, CommandHandler

with open("users.json", "r", encoding="utf-8") as f:
    USERS = json.load(f)

with open("devir.json", "r", encoding="utf-8") as f:
    DEVIRS = json.load(f)

PANEL = {
    "url": os.environ.get("PANEL2_URL"),
    "username": os.environ.get("PANEL2_USER"),
    "password": os.environ.get("PANEL2_PASS")
}

GRUPLAR = {
    "MALEFİZ": ["SKY02","SKY03","SKY06","SKY07","SKY12","SKY13","SKY14","SKY16","SKY17",
                "SKY21","SKY22","SKY23","SKY24","SKY25","SKY29","SKY30","SKY37","SKY46",
                "SKY47","SKY48","SKY49","SKY58","SKY96"],
    "RASPUTİN": ["SKY04","SKY08","SKY11","SKY20","SKY34","SKY36","SKY39","SKY41","SKY42","SKY51",
                 "SKY65","SKY66","SKY67","SKY69","SKY70","SKY72","SKY73","SKY32","SKY77","SKY57","SKY98","SKY112","SKY114","SKY119"],
    "EFE": ["SKY09","SKY10","SKY27","SKY31","SKY40","SKY43","SKY50","SKY53","SKY55","SKY59","SKY61",
            "SKY62","SKY93","SKY94","SKY99","SKY100","SKY101","SKY103","SKY104","SKY105"],
    "DAYI": ["SKY75","SKY76","SKY83","SKY84","SKY86","SKY87"],
    "MEHMET ELVERDİ": ["SKY71","SKY80","SKY81","SKY82","SKY89","SKY15","SKY95"],
    "ALFİE": ["SKY18","SKY33","SKY54"],
    "SARRAF": ["SKY28","SKY44","SKY63"],
    "CAVİT": ["SKY35","SKY88","SKY19","SKY118"],
    "TOM HARDY": ["SKY26"],
    "BELİER": ["SKY45"],
    "GOOGLE": ["SKY52"],
    "KARTAL": ["SKY68"],
    "FAVELA": ["SKY74"],
    "XAR": ["SKY79","SKY113","SKY120"],
    "MAXWEL": ["SKY85","SKY64"],
    "GECEBEY": ["SKY05"],
    "WALTERWHİTE": ["SKY60"],
    "MEMATİ": ["SKY78","SKY90","SKY91"],
    "METEHAN": ["SKY97"],
    "CİCİ": ["SKY38","SKY56","SKY92"],
    "FRED": ["SKY106","SKY107","SKY108","SKY109","SKY110","SKY111","SKY115","SKY116","SKY117"],
    "BOŞ": ["SKY121"]
}
}

def normalize_command(name):
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower().replace(" ", "")
    name = re.sub(r"[^a-z0-9_]", "", name)
    return name


async def create_panel_session(panel_config):
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx))

    login_url = f"{panel_config['url']}/login"
    reports_url = f"{panel_config['url']}/reports/quickly"

    async with session.get(login_url) as r:
        text = await r.text()

    token = ""
    for line in text.splitlines():
        if 'name="_token"' in line:
            token = line.split('value="')[1].split('"')[0]
            break

    await session.post(login_url, data={
        "_token": token,
        "email": panel_config['username'],
        "password": panel_config['password']
    })

    async with session.get(reports_url) as r:
        text = await r.text()

    csrf = ""
    for line in text.splitlines():
        if 'csrf-token' in line:
            csrf = line.split('content="')[1].split('"')[0]
            break

    return session, csrf


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
        delivery = float(data.get("delivery", [0, 0])[1] if len(data.get("delivery", [])) > 1 else 0)

        return deposit - withdraw - delivery
    except:
        return 0.0


def create_group_handler(grup_adi):

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

        skylar = GRUPLAR[grup_adi]

        session, csrf = await create_panel_session(PANEL)

        mesaj = f"📌 {grup_adi} ({len(skylar)})\n"

        tasks = []
        keys = []

        for s in skylar:
            key = s.strip().upper()

            if key not in USERS:
                mesaj += f"{key} ❌\n"
                continue

            keys.append(key)
            tasks.append(fetch_amount(session, PANEL["url"], csrf, USERS[key]["uuid"]))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        grup_total = 0.0

        for key, result in zip(keys, results):
            if isinstance(result, Exception):
                result = 0.0

            total = result + float(DEVIRS.get(key, 0))
            grup_total += total

            mesaj += f"{key} {total:,.2f} ₺\n"

        mesaj += f"\n🔥 Toplam: {grup_total:,.2f} ₺"

        await session.close()
        await update.message.reply_text(mesaj)

    return handler


# 🔥 HELP KOMUTU
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    komutlar = "\n".join("/" + normalize_command(g) for g in GRUPLAR)

    await update.message.reply_text("📌 KOMUTLAR:\n\n" + komutlar)


if __name__ == "__main__":

    BOT_TOKEN = os.environ.get("BOT_TOKEN")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # 🔥 GRUP KOMUTLARI
    for grup in GRUPLAR:
        cmd = normalize_command(grup)
        app.add_handler(CommandHandler(cmd, create_group_handler(grup)))

    # 🔥 HELP
    app.add_handler(CommandHandler("help", help_command))

    print("Bot çalışıyor...")
    app.run_polling()
