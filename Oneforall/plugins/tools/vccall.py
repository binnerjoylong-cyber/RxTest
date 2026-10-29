import asyncio
from datetime import datetime
from logging import getLogger
from typing import Dict, Set

from pyrogram import filters
from pyrogram.types import Message
from pyrogram.raw import functions

from Oneforall import app
from Oneforall.utils.database import get_assistant

LOGGER = getLogger(__name__)

# ───────── CONFIG ─────────
VC_LOG_CHANNEL_ID = -1003813864849  # PUT YOUR VC LOG CHANNEL ID

# ───────── STATE ─────────
vc_active_users: Dict[int, Set[int]] = {}
active_vc_chats: Set[int] = set()
vc_logging_status: Dict[int, bool] = {}

# ───────── SMALL CAPS ─────────
def to_small_caps(text: str):
    mapping = {
        "a":"ᴀ","b":"ʙ","c":"ᴄ","d":"ᴅ","e":"ᴇ","f":"ꜰ","g":"ɢ","h":"ʜ","i":"ɪ","j":"ᴊ",
        "k":"ᴋ","l":"ʟ","m":"ᴍ","n":"ɴ","o":"ᴏ","p":"ᴘ","q":"ǫ","r":"ʀ","s":"s","t":"ᴛ",
        "u":"ᴜ","v":"ᴠ","w":"ᴡ","x":"x","y":"ʏ","z":"ᴢ",
        "A":"ᴀ","B":"ʙ","C":"ᴄ","D":"ᴅ","E":"ᴇ","F":"ꜰ","G":"ɢ","H":"ʜ","I":"ɪ","J":"ᴊ",
        "K":"ᴋ","L":"ʟ","M":"ᴍ","N":"ɴ","O":"ᴏ","P":"ᴘ","Q":"ǫ","R":"ʀ","S":"s","T":"ᴛ",
        "U":"ᴜ","V":"ᴠ","W":"ᴡ","X":"x","Y":"ʏ","Z":"ᴢ"
    }
    return "".join(mapping.get(c, c) for c in text)

# ───────── STATUS ─────────
async def get_vc_logger_status(chat_id: int) -> bool:
    return vc_logging_status.get(chat_id, False)

# ───────── VC LOGGER COMMAND ─────────
@app.on_message(filters.command("vclogger", prefixes=["/"]) & filters.group)
async def vclogger_command(_, message: Message):
    chat_id = message.chat.id
    args = message.text.split()

    if len(args) == 1:
        status = await get_vc_logger_status(chat_id)
        return await message.reply(
            f"🎧 <b>ᴠ¢ ℓσggєʀ:</b> <b>{to_small_caps(str(status))}</b>\n\n"
            "➤ <code>/vclogger on</code>\n"
            "➤ <code>/vclogger off</code>"
        )

    arg = args[1].lower()

    if arg in ("on", "enable", "yes"):
        vc_logging_status[chat_id] = True
        active_vc_chats.add(chat_id)
        asyncio.create_task(monitor_vc_chat(chat_id))
        await message.reply("✅ <b>ᴠ¢ ℓσggєʀ ᴇɴαвℓє∂</b>")

    elif arg in ("off", "disable", "no"):
        vc_logging_status[chat_id] = False
        active_vc_chats.discard(chat_id)
        vc_active_users.pop(chat_id, None)
        await message.reply("🚫 <b>ᴠ¢ ℓσggєʀ ∂ιѕαвℓє∂</b>")

# ───────── GET PARTICIPANTS ─────────
async def get_group_call_participants(userbot, peer):
    try:
        full = await userbot.invoke(functions.channels.GetFullChannel(channel=peer))
        if not full.full_chat.call:
            return []

        call = full.full_chat.call
        res = await userbot.invoke(
            functions.phone.GetGroupParticipants(
                call=call,
                ids=[],
                sources=[],
                offset="",
                limit=100
            )
        )
        return res.participants
    except Exception:
        return []

# ───────── MONITOR VC ─────────
async def monitor_vc_chat(chat_id: int):
    userbot = await get_assistant(chat_id)
    if not userbot:
        return

    while chat_id in active_vc_chats and await get_vc_logger_status(chat_id):

        try:
            peer = await userbot.resolve_peer(chat_id)
            participants = await get_group_call_participants(userbot, peer)

            new_users = {
                p.peer.user_id
                for p in participants
                if hasattr(p.peer, "user_id")
            }

            old_users = vc_active_users.get(chat_id, set())

            for uid in new_users - old_users:
                asyncio.create_task(handle_user_join(chat_id, uid, userbot))

            for uid in old_users - new_users:
                asyncio.create_task(handle_user_leave(chat_id, uid, userbot))

            vc_active_users[chat_id] = new_users

        except Exception as e:
            LOGGER.error(f"VC Monitor Error: {e}")

        await asyncio.sleep(5)

# ───────── JOIN ─────────
async def handle_user_join(chat_id: int, user_id: int, userbot):
    try:
        user = await userbot.get_users(user_id)
        chat = await app.get_chat(chat_id)
        now = datetime.now().strftime("%d %b %Y • %H:%M:%S")

        msg_text = (
            f"<blockquote expandable>🎶 <b>ᴠ¢ υѕєʀ ᴊσιηєᴅ</b>\n\n"
            f"👤 {to_small_caps(user.first_name)}\n"
            f"🧬 {user.id}\n"
            f"💌 {chat.title}\n"
            f"⏳ {now}</blockquote expandable>"
        )

        sent = await app.send_message(chat_id, msg_text)
        await app.send_message(VC_LOG_CHANNEL_ID, msg_text)

        await asyncio.sleep(4)
        try:
            await sent.delete()
        except:
            pass

    except Exception as e:
        LOGGER.error(f"Join Log Error: {e}")

# ───────── LEAVE ─────────
async def handle_user_leave(chat_id: int, user_id: int, userbot):
    try:
        user = await userbot.get_users(user_id)
        chat = await app.get_chat(chat_id)
        now = datetime.now().strftime("%d %b %Y • %H:%M:%S")

        msg_text = (
            f"<blockquote>🌌 <b>ᴠ¢ υѕєʀ ℓєƒт</b>\n\n"
            f"👤 {to_small_caps(user.first_name)}\n"
            f"🧬 {user.id}\n"
            f"💌 {chat.title}\n"
            f"⏳ {now}</blockquote>"
        )

        sent = await app.send_message(chat_id, msg_text)
        await app.send_message(VC_LOG_CHANNEL_ID, msg_text)

        await asyncio.sleep(4)
        try:
            await sent.delete()
        except:
            pass

    except Exception as e:
        LOGGER.error(f"Leave Log Error: {e}")

# ───────── VC MEMBERS COMMAND ─────────
@app.on_message(filters.command(["vcmembers", "seevc"], prefixes=["/"]) & filters.group)
async def vcmembers_command(_, message: Message):
    chat_id = message.chat.id
    userbot = await get_assistant(chat_id)

    if not userbot:
        return await message.reply("⚠️ No assistant available.")

    participants = await get_group_call_participants(
        userbot,
        await userbot.resolve_peer(chat_id)
    )

    if not participants:
        return await message.reply("ℹ️ ᴠ¢ ɪѕ ᴇᴍᴘᴛʏ.")

    msg_text = "<blockquote>🌟 <b>ᴠ¢ мємвєяѕ</b>\n\n"

    for p in participants:
        if hasattr(p.peer, "user_id"):
            user = await userbot.get_users(p.peer.user_id)

            video = getattr(p, "video", False)
            screen = getattr(p, "presentation", False)
            hand = getattr(p, "raise_hand_rating", None) is not None
            muted = getattr(p, "muted", False)
            speaking = getattr(p, "active_date", None) is not None
            left = getattr(p, "left", False)

            msg_text += (
                f"<blockquote expandable>➜ɴᴀᴍᴇ: {user.first_name}\n"
                f" ɪᴅ: {user.id}\n"
                f" ᴜsᴇʀɴᴀᴍᴇ: @{user.username if user.username else 'None'}\n"
                f" ᴠɪᴅᴇᴏ sʜᴀʀɪɴɢ: {video}\n"
                f" sᴄʀᴇᴇɴ sʜᴀʀɪɴɢ: {screen}\n"
                f" ɪs ʜᴀɴᴅ ʀᴀɪsᴇᴅ: {hand}\n"
                f" ᴍᴜᴛᴇᴅ: {muted}\n"
                f" <b>sᴘᴇᴀᴋɪɴɢ</b>: {speaking}\n"
                f" <b>ʟᴇғᴛᴇᴅ ғʀᴏᴍ ɢʀᴏᴜᴘ:</b> {left}</blockquote expandable>\n\n"
            )

    msg_text += "</blockquote>"

    await message.reply(msg_text)