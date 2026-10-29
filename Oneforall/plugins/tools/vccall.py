import asyncio
from datetime import datetime
from logging import getLogger
from typing import Dict, Set

from pyrogram import enums, filters
from pyrogram.raw import functions, types as raw_types
from pyrogram.types import Message

import config
from Oneforall import app
from Oneforall.misc import SUDOERS
from Oneforall.utils.database import get_assistant, is_nonadmin_chat

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
        "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ", "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ",
        "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ", "s": "s", "t": "ᴛ",
        "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x", "y": "ʏ", "z": "ᴢ",
        "A": "ᴀ", "B": "ʙ", "C": "ᴄ", "D": "ᴅ", "E": "ᴇ", "F": "ꜰ", "G": "ɢ", "H": "ʜ", "I": "ɪ", "J": "ᴊ",
        "K": "ᴋ", "L": "ʟ", "M": "ᴍ", "N": "ɴ", "O": "ᴏ", "P": "ᴘ", "Q": "ǫ", "R": "ʀ", "S": "s", "T": "ᴛ",
        "U": "ᴜ", "V": "ᴠ", "W": "ᴡ", "X": "x", "Y": "ʏ", "Z": "ᴢ"
    }
    return "".join(mapping.get(c, c) for c in text)


# ───────── COMPREHENSIVE PERMISSION CHECK (ADMIN / OWNER / SUDO / AUTH) ─────────
async def is_admin_or_owner(message: Message) -> bool:
    user_id = message.from_user.id if message.from_user else None

    # Anonymous admin handling
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return True

    if not user_id:
        return False

    # Check SUDO users & Bot Owner
    if user_id in SUDOERS or user_id == config.OWNER_ID:
        return True

    # Check chat admin list directly without depending on bot rights
    try:
        async for admin in app.get_chat_members(message.chat.id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
            if admin.user and admin.user.id == user_id:
                return True
    except Exception:
        pass

    # Check single member status fallback
    try:
        m = await app.get_chat_member(message.chat.id, user_id)
        if m.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
            return True
    except Exception:
        pass

    # Auth chat check from database if configured
    try:
        if await is_nonadmin_chat(message.chat.id):
            return True
    except Exception:
        pass

    return False


# ───────── STATUS ─────────
async def get_vc_logger_status(chat_id: int) -> bool:
    return vc_logging_status.get(chat_id, False)


# ───────── BULLETPROOF GROUP CALL RESOLVER (NO BOT ADMIN REQUIRED) ─────────
async def get_group_call_participants(client, chat_id: int):
    try:
        # Directly build raw peer
        peer = await client.resolve_peer(chat_id)
        call = None

        if isinstance(peer, raw_types.InputPeerChannel):
            full = await client.invoke(
                functions.channels.GetFullChannel(
                    channel=raw_types.InputChannel(
                        channel_id=peer.channel_id,
                        access_hash=peer.access_hash,
                    )
                )
            )
            call = getattr(full.full_chat, "call", None)
        elif isinstance(peer, raw_types.InputPeerChat):
            full = await client.invoke(functions.messages.GetFullChat(chat_id=peer.chat_id))
            call = getattr(full.full_chat, "call", None)

        if not call:
            return []

        res = await client.invoke(
            functions.phone.GetGroupParticipants(
                call=call,
                ids=[],
                sources=[],
                offset="",
                limit=100,
            )
        )
        return res.participants
    except Exception as e:
        LOGGER.error(f"VC Participant fetch failed: {e}")
        return []


# ───────── VC LOGGER COMMAND ─────────
@app.on_message(filters.command("vclogger", prefixes=["/", "!"]) & filters.group)
async def vclogger_command(_, message: Message):
    chat_id = message.chat.id

    if not await is_admin_or_owner(message):
        return await message.reply("❌ **Sirf group admins, owner ya sudo users hi VC logger control kar sakte hain.**")

    args = message.text.split()

    if len(args) == 1:
        status = await get_vc_logger_status(chat_id)
        return await message.reply(
            f"🎧 <b>ᴠ¢ ℓσggєʀ:</b> <b>{to_small_caps('Enabled' if status else 'Disabled')}</b>\n\n"
            "➤ <code>/vclogger on</code>\n"
            "➤ <code>/vclogger off</code>"
        )

    arg = args[1].lower()

    if arg in ("on", "enable", "yes"):
        if await get_vc_logger_status(chat_id):
            return await message.reply("ℹ️ <b>ᴠ¢ ℓσggєʀ already enabled hai.</b>")
        vc_logging_status[chat_id] = True
        active_vc_chats.add(chat_id)
        asyncio.create_task(monitor_vc_chat(chat_id))
        await message.reply("✅ <b>ᴠ¢ ℓσggєʀ ᴇɴαвℓє∂</b>")

    elif arg in ("off", "disable", "no"):
        if not await get_vc_logger_status(chat_id):
            return await message.reply("ℹ️ <b>ᴠ¢ ℓσggєʀ already disabled hai.</b>")
        vc_logging_status[chat_id] = False
        active_vc_chats.discard(chat_id)
        vc_active_users.pop(chat_id, None)
        await message.reply("🚫 <b>ᴠ¢ ℓσggєʀ ∂ιѕαвℓє∂</b>")


# ───────── MONITOR VC ─────────
async def monitor_vc_chat(chat_id: int):
    userbot = await get_assistant(chat_id)

    while chat_id in active_vc_chats and await get_vc_logger_status(chat_id):
        try:
            participants = await get_group_call_participants(app, chat_id)
            if not participants and userbot:
                participants = await get_group_call_participants(userbot, chat_id)

            new_users = set()
            for p in participants:
                uid = getattr(p, "user_id", None)
                if not uid and hasattr(p, "peer") and hasattr(p.peer, "user_id"):
                    uid = p.peer.user_id
                if uid:
                    new_users.add(uid)

            old_users = vc_active_users.get(chat_id, set())

            for uid in new_users - old_users:
                asyncio.create_task(handle_user_join(chat_id, uid))

            for uid in old_users - new_users:
                asyncio.create_task(handle_user_leave(chat_id, uid))

            vc_active_users[chat_id] = new_users

        except Exception as e:
            LOGGER.error(f"VC Monitor Error: {e}")

        await asyncio.sleep(5)


# ───────── JOIN LOG ─────────
async def handle_user_join(chat_id: int, user_id: int):
    try:
        user = await app.get_users(user_id)
        chat = await app.get_chat(chat_id)
        now = datetime.now().strftime("%d %b %Y • %H:%M:%S")

        msg_text = (
            "<blockquote expandable>🎶 <b>ᴠ¢ υѕєʀ ᴊσιηєᴅ</b>\n\n"
            f"👤 {to_small_caps(user.first_name)}\n"
            f"🧬 <code>{user.id}</code>\n"
            f"💌 {chat.title}\n"
            f"⏳ {now}</blockquote>"
        )

        sent = await app.send_message(chat_id, msg_text)
        try:
            await app.send_message(VC_LOG_CHANNEL_ID, msg_text)
        except Exception:
            pass

        await asyncio.sleep(4)
        try:
            await sent.delete()
        except Exception:
            pass

    except Exception as e:
        LOGGER.error(f"Join Log Error: {e}")


# ───────── LEAVE LOG ─────────
async def handle_user_leave(chat_id: int, user_id: int):
    try:
        user = await app.get_users(user_id)
        chat = await app.get_chat(chat_id)
        now = datetime.now().strftime("%d %b %Y • %H:%M:%S")

        msg_text = (
            "<blockquote>🌌 <b>ᴠ¢ υѕєʀ ℓєƒт</b>\n\n"
            f"👤 {to_small_caps(user.first_name)}\n"
            f"🧬 <code>{user.id}</code>\n"
            f"💌 {chat.title}\n"
            f"⏳ {now}</blockquote>"
        )

        sent = await app.send_message(chat_id, msg_text)
        try:
            await app.send_message(VC_LOG_CHANNEL_ID, msg_text)
        except Exception:
            pass

        await asyncio.sleep(4)
        try:
            await sent.delete()
        except Exception:
            pass

    except Exception as e:
        LOGGER.error(f"Leave Log Error: {e}")


# ───────── VC MEMBERS COMMAND (OPEN FOR EVERYONE - NO BOT ADMIN REQUIRED) ─────────
@app.on_message(filters.command(["vcmembers", "seevc"], prefixes=["/", "!"]) & filters.group)
async def vcmembers_command(_, message: Message):
    chat_id = message.chat.id

    # 1. Fetch through Main Bot directly
    participants = await get_group_call_participants(app, chat_id)

    # 2. Fallback to Assistant if Bot gets empty list
    if not participants:
        userbot = await get_assistant(chat_id)
        if userbot:
            participants = await get_group_call_participants(userbot, chat_id)

    if not participants:
        return await message.reply("ℹ️ **ᴠ¢ ɪѕ ᴇᴍᴘᴛʏ / ɴᴏ ᴀᴄᴛɪᴠᴇ ᴄᴀʟʟ.**")

    final_output = [
        "<blockquote>🌟 <u><b>ᴠ¢ ᴀᴄᴛɪᴠᴇ ᴍᴇᴍʙᴇʀs</b></u>\n"
        f"📊 <b>ᴛᴏᴛᴀʟ ᴜsᴇʀs :</b> <code>{len(participants)}</code></blockquote>\n"
    ]

    for p in participants:
        uid = getattr(p, "user_id", None)
        if not uid and hasattr(p, "peer") and hasattr(p.peer, "user_id"):
            uid = p.peer.user_id

        if not uid:
            continue

        try:
            user = await app.get_users(uid)
        except Exception:
            continue

        video = "Yes" if getattr(p, "video", False) else "No"
        screen = "Yes" if getattr(p, "presentation", False) else "No"
        hand = "Yes" if getattr(p, "raise_hand_rating", None) is not None else "No"
        muted = "Yes" if getattr(p, "muted", False) else "No"
        speaking = "Yes" if getattr(p, "active_date", None) is not None else "No"
        left = "Yes" if getattr(p, "left", False) else "No"

        final_output.append(
            f"<blockquote expandable>"
            f"👤 <b>ɴᴀᴍᴇ:</b> {user.mention}\n"
            f"🆔 <b>ɪᴅ:</b> <code>{user.id}</code>\n"
            f"🔗 <b>ᴜsᴇʀɴᴀᴍᴇ:</b> @{user.username if user.username else 'None'}\n"
            f"📹 <b>ᴠɪᴅᴇᴏ:</b> <code>{video}</code> | 💻 <b>sᴄʀᴇᴇɴ:</b> <code>{screen}</code>\n"
            f"✋ <b>ʜᴀɴᴅ:</b> <code>{hand}</code> | 🎙️ <b>ᴍᴜᴛᴇᴅ:</b> <code>{muted}</code>\n"
            f"🔊 <b>sᴘᴇᴀᴋɪɴɢ:</b> <code>{speaking}</code> | 🚪 <b>ʟᴇғᴛ:</b> <code>{left}</code>"
            f"</blockquote>\n"
        )

    msg_text = "\n".join(final_output)

    if len(msg_text) > 4096:
        for chunk in [msg_text[i:i + 4000] for i in range(0, len(msg_text), 4000)]:
            await message.reply(chunk)
    else:
        await message.reply(msg_text)
