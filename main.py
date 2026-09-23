# Dk_userbotx - main.py
import asyncio
import os
import sys
import random
import time
from flask import Flask
from threading import Thread
from pymongo import MongoClient

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from pyrogram import Client, filters, errors, handlers, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatType

BOT_START_TIME = time.time()

def env_int(name, default=0):
    try:
        return int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        return default

API_ID = env_int("API_ID")
API_HASH = os.getenv("API_HASH", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
LOG_GROUP = env_int("LOG_GROUP")
MONGO_URL = os.getenv("MONGO_URL", "").strip()
OWNER_ID = env_int("OWNER_ID")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "").strip()
START_VIDEO = ""
ALIVE_IMG = ""

FSUB_CHANNELS = [
    x.strip() for x in os.getenv("FSUB_CHANNELS", "").split(",") if x.strip()
]

if not API_ID or not API_HASH or not BOT_TOKEN:
    raise RuntimeError("Missing API_ID, API_HASH or BOT_TOKEN in environment.")
if not MONGO_URL:
    raise RuntimeError("Missing MONGO_URL in environment.")
if not OWNER_ID:
    raise RuntimeError("Missing OWNER_ID in environment.")

try:
    mongo_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
    mongo_client.admin.command("ping")
    db = mongo_client["CoderNovaBotDB"]
    sessions_col = db["sessions"]
    print("[SUCCESS] MongoDB Connected!")
except Exception as e:
    print(f"[ERROR] MongoDB Failed: {e}")
    sys.exit(1)

def load_local_sessions():
    try:
        return {
            str(doc["user_id"]): doc["session_str"]
            for doc in sessions_col.find({})
            if doc.get("session_str")
        }
    except Exception:
        return {}

def save_local_session(user_id, session_str):
    sessions_col.update_one(
        {"user_id": str(user_id)},
        {"$set": {"session_str": session_str}},
        upsert=True,
    )

def get_readable_time(seconds):
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{days}d, {hours:02d}:{minutes:02d}:{seconds:02d}" if days else f"{hours:02d}:{minutes:02d}:{seconds:02d}"

app = Flask(__name__)

@app.route("/")
def home():
    return "Dk_userbotx Online"

def run_web():
    port = env_int("PORT", 8080)
    app.run(host="0.0.0.0", port=port, use_reloader=False)

bot = Client("CoderNovaGen", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_data = {}
active_tasks = {}
running_ubots = {}
pm_guard_data = {}

main_buttons = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📲 ADD ACCOUNT", callback_data="add_btn"),
        InlineKeyboardButton("🛠️ HELP", callback_data="help_btn"),
    ],
    [
        InlineKeyboardButton(
            "👑 OWNER",
            url=f"https://t.me/{OWNER_USERNAME.replace('@','') or 'CoderNova'}",
        ),
        InlineKeyboardButton("📢 UPDATE", url="https://t.me/NovaBot_Support"),
    ],
    [InlineKeyboardButton("❌ CLOSE", callback_data="close")],
])

DAILY_CHATS = [
    "ʜɪɪ {mention}",
    "ᴋᴀɪsᴇ ʜᴏ {mention}",
    "ᴋʏᴀ ᴋʀ ʀʜᴇ ʜᴏ {mention}",
    "ᴋʜᴀ sᴇ ʜᴏ {mention}",
    "ᴋʏᴀ ᴋʀᴛᴇ ʜᴏ {mention}",
    "ʀᴀᴅʜᴇ ʀᴀᴅʜᴇ {mention}",
    "ᴊᴀɪ sʜʀᴇᴇ ʀᴀᴍ {mention}",
    "ᴏʀ sᴜɴᴀᴏ {mention}",
    "ᴠᴄ ᴀᴀʏᴀ ᴋʀ ʏʀ {mention}",
    "ɢʀᴏᴜᴘ ᴍᴇ ᴀᴀʏᴀ ᴋʀ ʏʀ {mention}",
]

RAID_TEXTS = [
    "😈 RAID MESSAGE",
    "😂 KYA HAAL HAI",
    "🔥 ACTIVE USER",
    "😎 HELLO BRO",
]

async def check_force_join(c, user_id):
    not_joined = []
    for channel in FSUB_CHANNELS:
        try:
            await c.get_chat_member(channel, user_id)
        except errors.UserNotParticipant:
            not_joined.append(channel)
        except Exception:
            pass
    return not_joined

async def alive_cmd(c, m):
    uptime = get_readable_time(time.time() - BOT_START_TIME)
    text = (
        "✨ **Dk_userbotx IS ALIVE** ✨\n\n"
        f"⏳ **Uptime:** `{uptime}`\n"
        f"👤 **User:** {c.me.mention}\n"
        f"👑 **Owner:** {OWNER_USERNAME or 'Not set'}\n\n"
        "✨ **I am alive** ✨"
    )
    try:
        await m.delete()
    except Exception:
        pass
    try:
        await c.send_message(m.chat.id, text)
    except Exception:
        pass

async def assistant_help_cmd(c, m):
    text = (
        "**Dk_userbotx Commands**\n\n"
        "`.help` - Show help\n"
        "`.alive` - Check status\n"
        "`.tagall [text]` - Tag members\n"
        "`.onetag` - Tag members with messages\n"
        "`.raid [count]` - Send raid messages to a replied message\n"
        "`.clone @username` - Clone profile\n"
        "`.stop` - Stop running tasks"
    )
    try:
        await m.delete()
    except Exception:
        pass
    await c.send_message(m.chat.id, text)

async def tagall_cmd(c, m):
    uid = c.me.id
    active_tasks[uid] = True
    parts = (m.text or "").split(None, 1)
    custom = parts[1] if len(parts) > 1 else "Hey {mention}"
    try:
        await m.delete()
    except Exception:
        pass

    try:
        async for member in c.get_chat_members(m.chat.id):
            if not active_tasks.get(uid):
                break
            user = member.user
            if not user or user.is_bot or user.is_deleted:
                continue
            mention = f"[{user.first_name or 'User'}](tg://user?id={user.id})"
            await c.send_message(m.chat.id, custom.replace("{mention}", mention))
            await asyncio.sleep(2)
    except errors.FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass

async def onetag_cmd(c, m):
    uid = c.me.id
    active_tasks[uid] = True
    try:
        await m.delete()
    except Exception:
        pass

    try:
        async for member in c.get_chat_members(m.chat.id):
            if not active_tasks.get(uid):
                break
            user = member.user
            if not user or user.is_bot or user.is_deleted:
                continue
            mention = f"[{user.first_name or 'User'}](tg://user?id={user.id})"
            await c.send_message(m.chat.id, random.choice(DAILY_CHATS).format(mention=mention))
            await asyncio.sleep(2)
    except errors.FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass

async def raid_cmd(c, m):
    uid = c.me.id
    if not m.reply_to_message:
        return await m.edit_text("❌ Reply to a message first.")
    try:
        count = int((m.text or "").split()[1])
    except (IndexError, ValueError):
        count = 10
    count = max(1, min(count, 50))
    active_tasks[uid] = True
    reply_id = m.reply_to_message.id
    try:
        await m.delete()
    except Exception:
        pass

    for _ in range(count):
        if not active_tasks.get(uid):
            break
        try:
            await c.send_message(
                m.chat.id,
                random.choice(RAID_TEXTS),
                reply_to_message_id=reply_id,
            )
            await asyncio.sleep(2)
        except errors.FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            break

async def clone_cmd(c, m):
    target = None
    if len(m.command) > 1:
        target = m.command[1]
    elif m.reply_to_message and m.reply_to_message.from_user:
        target = m.reply_to_message.from_user.id

    if not target:
        return await m.edit_text("❌ Usage: `.clone @username` or reply to a user.")

    try:
        status = await m.edit_text("🔄 **Cloning...**")
        user = await c.get_users(target)
        chat = await c.get_chat(user.id)
        photos = [p async for p in c.get_chat_photos(user.id, limit=1)]

        if photos:
            try:
                path = await c.download_media(photos[0].file_id)
                await c.set_profile_photo(photo=path)
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

        await c.update_profile(
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            bio=chat.bio or "",
        )
        await status.edit("✅ **Profile cloned successfully.**")
    except Exception as e:
        try:
            await status.edit(f"❌ **Failed:** `{e}`")
        except Exception:
            pass

async def stop_cmd(c, m):
    active_tasks[c.me.id] = False
    await m.edit_text("🚫 **All running tasks stopped.**")

async def pm_guard_handler(c, m):
    if m.chat.type != ChatType.PRIVATE or not m.from_user:
        return
    if m.from_user.is_bot or m.from_user.id == c.me.id or m.from_user.id == OWNER_ID:
        return

    if getattr(m.from_user, "is_contact", False):
        return

    uid = c.me.id
    sender = m.from_user.id
    pm_guard_data.setdefault(uid, {})
    pm_guard_data[uid][sender] = pm_guard_data[uid].get(sender, 0) + 1
    count = pm_guard_data[uid][sender]

    if count >= 5:
        try:
            await m.reply_text("🚨 PM limit exceeded. You have been blocked.")
            await c.block_user(sender)
        except Exception:
            pass
        pm_guard_data[uid].pop(sender, None)
    else:
        try:
            await m.reply_text(f"🔒 Owner is offline. Warning `{count}/5`.")
        except Exception:
            pass

def register_ubot_handlers(ubot):
    ubot.add_handler(handlers.MessageHandler(assistant_help_cmd, filters.command("help", ".") & filters.me))
    ubot.add_handler(handlers.MessageHandler(alive_cmd, filters.command("alive", ".") & filters.me))
    ubot.add_handler(handlers.MessageHandler(tagall_cmd, filters.command("tagall", ".") & filters.me))
    ubot.add_handler(handlers.MessageHandler(onetag_cmd, filters.command("onetag", ".") & filters.me))
    ubot.add_handler(handlers.MessageHandler(raid_cmd, filters.command("raid", ".") & filters.me))
    ubot.add_handler(handlers.MessageHandler(clone_cmd, filters.command("clone", ".") & filters.me))
    ubot.add_handler(handlers.MessageHandler(stop_cmd, filters.command("stop", ".") & filters.me))

    ubot.add_handler(
    handlers.MessageHandler(pm_guard_handler, filters.private & ~filters.me),
    group=2
)

START_TEXT = (
    "⚡ **Welcome to Dk_userbotx** ⚡\n\n"
    "Hey {mention}, use the buttons below to manage your userbot.\n\n"
    "✨ **I am alive** ✨"
)

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(c, m):
    unjoined = await check_force_join(c, m.from_user.id)
    if unjoined:
        buttons = [
            [InlineKeyboardButton(f"📥 Join {ch}", url=f"https://t.me/{ch.lstrip('@')}")]
            for ch in unjoined
        ]
        buttons.append([InlineKeyboardButton("🔄 Verify", callback_data="verify_fsub")])
        return await m.reply_text(
            "⚠️ **Please join the required channel(s) first.**",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    text = START_TEXT.format(mention=m.from_user.mention)
    await m.reply_text(text, reply_markup=main_buttons)

@bot.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast_cmd(c, m):
    if not m.reply_to_message:
        return await m.reply_text("❌ Reply to a message to broadcast it.")
    status = await m.reply_text("📢 Broadcasting...")
    success = failed = 0
    for user_id in load_local_sessions():
        try:
            await m.reply_to_message.forward(int(user_id))
            success += 1
            await asyncio.sleep(0.3)
        except Exception:
            failed += 1
    await status.edit(f"✅ Done\n🟢 Success: `{success}`\n🔴 Failed: `{failed}`")

@bot.on_message(filters.command("remove_all") & filters.user(OWNER_ID))
async def remove_all_cmd(c, m):
    sessions_col.delete_many({})
    for ubot in list(running_ubots.values()):
        try:
            await ubot.stop()
        except Exception:
            pass
    running_ubots.clear()
    await m.reply_text("🗑️ All saved sessions removed and userbots stopped.")

@bot.on_callback_query()
async def handle_callbacks(c, q):
    if q.data == "close":
        try:
            await q.message.delete()
        except Exception:
            pass
    elif q.data == "verify_fsub":
        unjoined = await check_force_join(c, q.from_user.id)
        if unjoined:
            await q.answer("❌ Please join all required channels.", show_alert=True)
        else:
            await q.message.delete()
            await bot.send_message(
                q.message.chat.id,
                START_TEXT.format(mention=q.from_user.mention),
                reply_markup=main_buttons,
            )
    elif q.data == "help_btn":
        await q.answer("Use .help in your userbot.", show_alert=True)
    elif q.data == "add_btn":
        await q.message.reply_text("📲 Send your phone number, e.g. +91xxxxxxxxxx")
        await q.message.delete()

@bot.on_message(filters.text & filters.private & ~filters.bot)
async def handle_steps(c, m):
    uid = m.from_user.id
    text = (m.text or "").strip()

    if text.startswith("+") and len(text) >= 8:
        old = user_data.get(uid)
        if old and old.get("client"):
            try:
                await old["client"].disconnect()
            except Exception:
                pass

        temp = Client(f"temp_{uid}", API_ID, API_HASH, in_memory=True)
        try:
            await temp.connect()
            sent = await temp.send_code(text)
            user_data[uid] = {
                "phone": text,
                "client": temp,
                "hash": sent.phone_code_hash,
            }
            await m.reply_text("📩 Enter OTP with spaces, e.g. `1 2 3 4 5`")
        except Exception as e:
            try:
                await temp.disconnect()
            except Exception:
                pass
            await m.reply_text(f"❌ `{e}`")

    elif uid in user_data and user_data[uid].get("hash") and text.replace(" ", "").isdigit():
        try:
            await user_data[uid]["client"].sign_in(
                user_data[uid]["phone"],
                user_data[uid]["hash"],
                text.replace(" ", ""),
            )
            await finalize_login(m, uid)
        except errors.SessionPasswordNeeded:
            user_data[uid]["step"] = "password"
            await m.reply_text("🔐 Enter your two-step verification password.")
        except Exception as e:
            await m.reply_text(f"❌ `{e}`")

    elif uid in user_data and user_data[uid].get("step") == "password":
        try:
            await user_data[uid]["client"].check_password(text)
            await finalize_login(m, uid)
        except Exception as e:
            await m.reply_text(f"❌ `{e}`")

async def finalize_login(m, uid):
    data = user_data.get(uid)
    if not data:
        return
    temp = data["client"]
    try:
        session_string = await temp.export_session_string()
        save_local_session(uid, session_string)
        try:
            await temp.disconnect()
        except Exception:
            pass

        if uid in running_ubots:
            try:
                await running_ubots[uid].stop()
            except Exception:
                pass

        ubot = Client(
            f"ubot_{uid}",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=session_string,
        )
        register_ubot_handlers(ubot)
        await ubot.start()
        running_ubots[uid] = ubot
        await bot.send_message(uid, "🎉 **Login successful! Your userbot is active.**")
    finally:
        user_data.pop(uid, None)

async def start_services():
    await bot.start()
    for user_id, session_string in load_local_sessions().items():
        try:
            uid = int(user_id)
            ubot = Client(
                f"ubot_{uid}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_string,
            )
            register_ubot_handlers(ubot)
            await ubot.start()
            running_ubots[uid] = ubot
            await asyncio.sleep(0.2)
        except Exception as e:
            print(f"[WARNING] Could not start userbot {user_id}: {e}")
    await idle()

if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    loop.run_until_complete(start_services())