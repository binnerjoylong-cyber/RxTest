import os
from io import BytesIO
from PIL import Image
from httpx import AsyncClient, Timeout
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import StickersetInvalid
from pyrogram.raw.functions.messages import GetStickerSet, UploadMedia
from pyrogram.raw.functions.stickers import AddStickerToSet, CreateStickerSet
from pyrogram.raw.types import (
    DocumentAttributeFilename,
    InputDocument,
    InputMediaUploadedDocument,
    InputStickerSetItem,
    InputStickerSetShortName,
)

from Oneforall import app

PREMIUM_EMOJI_LEFT = "5895221391220804630"
PREMIUM_EMOJI_RIGHT = "5895648298085125845"
PRIMARY_BG_COLOR = "#1b1429"
ACCENT_COLOR = "#7b5bf2"

# Direct Working Quotly REST Endpoints (Cloudflare SSL Bypass)
QUOTLY_SERVERS = [
    "https://quotly.herokuapp.com/generate",
    "https://quote-generator.deno.dev/generate",
    "https://bot.lyo.su/quote/generate.png",
]

client_http = AsyncClient(
    http2=False,
    verify=False,
    headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    },
    timeout=Timeout(30),
)


class QuotlyException(Exception):
    pass


# -------------------------------------------------------------------------
# QUOTLY HELPERS
# -------------------------------------------------------------------------

async def get_sender_id(msg: Message) -> int:
    if msg.forward_date:
        if msg.forward_from:
            return msg.forward_from.id
        if msg.forward_from_chat:
            return msg.forward_from_chat.id
        return 1
    if msg.from_user:
        return msg.from_user.id
    if msg.sender_chat:
        return msg.sender_chat.id
    return 1


async def get_sender_name(msg: Message) -> str:
    if msg.forward_date:
        if msg.forward_sender_name:
            return msg.forward_sender_name
        if msg.forward_from:
            return f"{msg.forward_from.first_name or ''} {msg.forward_from.last_name or ''}".strip()
        if msg.forward_from_chat:
            return msg.forward_from_chat.title or "Channel"
        return "Unknown"
    if msg.from_user:
        return f"{msg.from_user.first_name or ''} {msg.from_user.last_name or ''}".strip()
    if msg.sender_chat:
        return msg.sender_chat.title or "Channel"
    return "Unknown"


async def get_sender_username(msg: Message) -> str:
    if msg.forward_date:
        if msg.forward_from and msg.forward_from.username:
            return msg.forward_from.username
        if msg.forward_from_chat and msg.forward_from_chat.username:
            return msg.forward_from_chat.username
        return ""
    if msg.from_user and msg.from_user.username:
        return msg.from_user.username
    if msg.sender_chat and msg.sender_chat.username:
        return msg.sender_chat.username
    return ""


async def pyrogram_to_quotly(messages: list, is_reply: bool = False):
    payload = {
        "type": "quote",
        "format": "png",
        "backgroundColor": PRIMARY_BG_COLOR,
        "messages": [],
    }

    for msg in messages:
        entities = []
        raw_entities = msg.entities or msg.caption_entities
        if raw_entities:
            for ent in raw_entities:
                entities.append({
                    "type": ent.type.name.lower(),
                    "offset": ent.offset,
                    "length": ent.length,
                })

        user_name = await get_sender_name(msg)
        msg_text = msg.text or msg.caption or ""

        msg_data = {
            "entities": entities,
            "chatId": await get_sender_id(msg),
            "text": msg_text,
            "avatar": True,
            "from": {
                "id": await get_sender_id(msg),
                "name": user_name,
                "username": await get_sender_username(msg),
                "type": "user",
                "color": ACCENT_COLOR,
            },
        }

        if is_reply and msg.reply_to_message:
            rep = msg.reply_to_message
            msg_data["replyMessage"] = {
                "name": await get_sender_name(rep),
                "text": rep.text or rep.caption or "",
                "chatId": await get_sender_id(rep),
            }

        payload["messages"].append(msg_data)

    last_error = ""
    for endpoint in QUOTLY_SERVERS:
        try:
            res = await client_http.post(endpoint, json=payload)
            if res.status_code == 200 and res.content:
                # Convert PNG to valid Telegram WEBP sticker
                img = Image.open(BytesIO(res.content))
                out = BytesIO()
                img.save(out, format="WEBP")
                out.name = "quote.webp"
                out.seek(0)
                return out
            last_error = f"HTTP {res.status_code}"
        except Exception as e:
            last_error = str(e)
            continue

    raise QuotlyException(last_error or "Quotly servers down")


# -------------------------------------------------------------------------
# QUOTE HANDLER (/q, /q p, /q r)
# -------------------------------------------------------------------------

@app.on_message(filters.command(["q", "quote"]) & filters.reply)
async def quotly_command(client: app, message: Message):
    status_msg = await message.reply_text(
        f'<emoji id="{PREMIUM_EMOJI_LEFT}">⚡</emoji> **Gᴇɴᴇʀᴀᴛɪɴɢ Qᴜᴏᴛᴇ...**'
    )

    try:
        args = message.text.split()[1:] if message.text else []
        arg = args[0].lower() if args else ""
        target_msg = message.reply_to_message

        # /q p ya /q r: Dono users ka conversation merge karega
        if arg in ["p", "r"]:
            if target_msg.reply_to_message:
                messages = [target_msg.reply_to_message, target_msg]
            else:
                messages = [target_msg]
            is_reply = False
        elif arg.isdigit():
            count = max(1, min(int(arg), 10))
            msg_ids = list(range(target_msg.id, target_msg.id + count))
            fetched = await client.get_messages(chat_id=message.chat.id, message_ids=msg_ids)
            messages = [m for m in fetched if m and not m.empty]
            is_reply = False
        else:
            messages = [target_msg]
            is_reply = bool(target_msg.reply_to_message)

        sticker_file = await pyrogram_to_quotly(messages, is_reply=is_reply)

        await message.reply_sticker(sticker=sticker_file)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(
            f'<emoji id="{PREMIUM_EMOJI_RIGHT}">❌</emoji> **Eʀʀᴏʀ:**\n'
            f'> `{str(e)}`'
        )


# -------------------------------------------------------------------------
# KANG HANDLER (/kang)
# -------------------------------------------------------------------------

async def convert_to_valid_sticker(image_path: str) -> BytesIO:
    im = Image.open(image_path)
    if im.mode != "RGBA":
        im = im.convert("RGBA")

    width, height = im.size
    if width > height:
        scale = 512 / width
        new_size = (512, int(height * scale))
    else:
        scale = 512 / height
        new_size = (int(width * scale), 512)

    im = im.resize(new_size, Image.Resampling.LANCZOS)
    output = BytesIO()
    im.save(output, format="WEBP")
    output.name = "sticker.webp"
    output.seek(0)
    return output


@app.on_message(filters.command(["kang"]) & filters.reply)
async def kang_command(client: app, message: Message):
    replied = message.reply_to_message
    if not (replied.photo or replied.sticker or replied.document):
        return await message.reply_text(
            f'<emoji id="{PREMIUM_EMOJI_RIGHT}">❌</emoji> **Kʀɪᴘʏᴀ ᴋɪsɪ ᴘʜᴏᴛᴏ, sᴛɪᴄᴋᴇʀ ʏᴀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴘᴀʀ ʀᴇᴘʟʏ ᴋᴀʀᴇɪɴ.**'
        )

    status_msg = await message.reply_text(
        f'<emoji id="{PREMIUM_EMOJI_LEFT}">⚡</emoji> **Pʀᴏᴄᴇssɪɴɢ Sᴛɪᴄᴋᴇʀ...**'
    )

    temp_path = None
    try:
        temp_path = await replied.download()
        sticker_data = await convert_to_valid_sticker(temp_path)

        user = message.from_user
        bot_user = await client.get_me()

        raw_doc = await client.save_file(sticker_data)
        media_doc = await client.invoke(
            UploadMedia(
                peer=await client.resolve_peer(message.chat.id),
                media=InputMediaUploadedDocument(
                    file=raw_doc,
                    mime_type="image/webp",
                    attributes=[DocumentAttributeFilename(file_name="sticker.webp")],
                ),
            )
        )
        input_document = InputDocument(
            id=media_doc.document.id,
            access_hash=media_doc.document.access_hash,
            file_reference=media_doc.document.file_reference,
        )

        pack_num = 1
        sticker_emoji = "✨"
        if len(message.command) > 1:
            sticker_emoji = message.command[1]
        elif replied.sticker and replied.sticker.emoji:
            sticker_emoji = replied.sticker.emoji

        pack_created = False
        while not pack_created:
            short_name = f"a{user.id}_pack{pack_num}_by_{bot_user.username}"
            pack_title = f"</> Kᴀɴɢ Sᴛᴀᴛɪᴄ #{pack_num}"

            try:
                sticker_set = await client.invoke(
                    GetStickerSet(
                        stickerset=InputStickerSetShortName(short_name=short_name),
                        hash=0,
                    )
                )

                if sticker_set.set.count >= 120:
                    pack_num += 1
                    continue

                await client.invoke(
                    AddStickerToSet(
                        stickerset=InputStickerSetShortName(short_name=short_name),
                        sticker=InputStickerSetItem(
                            document=input_document,
                            emoji=sticker_emoji,
                        ),
                    )
                )
                pack_created = True

            except StickersetInvalid:
                await client.invoke(
                    CreateStickerSet(
                        user_id=await client.resolve_peer(user.id),
                        title=pack_title,
                        short_name=short_name,
                        stickers=[
                            InputStickerSetItem(
                                document=input_document,
                                emoji=sticker_emoji,
                            )
                        ],
                    )
                )
                pack_created = True

        pack_url = f"https://t.me/addstickers/{short_name}"
        button = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Oᴘᴇɴ Pᴀᴄᴋ", url=pack_url)]]
        )

        await status_msg.edit_text(
            f'<emoji id="{PREMIUM_EMOJI_LEFT}">✨</emoji> **Kᴀɴɢᴇᴅ.**\n\n'
            f'> **Pᴀᴄᴋ:** `{pack_title}`\n'
            f'> **Tʏᴘᴇ:** `ʀᴇɢᴜʟᴀʀ`\n'
            f'> **Eᴍᴏᴊɪ:** {sticker_emoji}',
            reply_markup=button,
        )

    except Exception as e:
        await status_msg.edit_text(
            f'<emoji id="{PREMIUM_EMOJI_RIGHT}">❌</emoji> **Eʀʀᴏʀ:**\n'
            f'> `{str(e)}`'
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# -------------------------------------------------------------------------
# MODULE & HELP INFO
# -------------------------------------------------------------------------

__MODULE__ = "Qᴜᴏᴛᴇ"

__HELP__ = """
**Qᴜᴏᴛᴇ & Sᴛɪᴄᴋᴇʀ Mᴏᴅᴜʟᴇ**

**Qᴜᴏᴛᴇ Cᴏᴍᴍᴀɴᴅs:**
> • `/q` : Qᴜᴏᴛᴇ ᴀ sɪɴɢʟᴇ ᴍᴇssᴀɢᴇ.
> • `/q p` ᴏʀ `/q r` : Qᴜᴏᴛᴇ ʀᴇᴘʟɪᴇᴅ ᴍᴇssᴀɢᴇ ᴡɪᴛʜ ɪᴛs ᴘᴀʀᴇɴᴛ ᴍᴇssᴀɢᴇ.
> • `/q [1-10]` : Qᴜᴏᴛᴇ ᴍᴜʟᴛɪᴘʟᴇ ᴍᴇssᴀɢᴇs ᴀᴛ ᴏɴᴄᴇ (ᴇ.ɢ. `/q 3`).

**Sᴛɪᴄᴋᴇʀ Kᴀɴɢ Cᴏᴍᴍᴀɴᴅs:**
> • `/kang` : Kᴀɴɢ sᴛɪᴄᴋᴇʀ, ᴘʜᴏᴛᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ʏᴏᴜʀ ᴘᴇʀsᴏɴᴀʟ ᴘᴀᴄᴋ.
> • `/kang [emoji]` : Kᴀɴɢ ᴡɪᴛʜ ʏᴏᴜʀ ᴄᴜsᴛᴏᴍ ᴇᴍᴏᴊɪ (ᴇ.ɢ. `/kang 🔥`).

**Nᴏᴛᴇ:**
> • Hᴀᴍᴇsʜᴀ ᴛᴀʀɢᴇᴛ ᴍᴇssᴀɢᴇ ʏᴀ ᴍᴇᴅɪᴀ ᴘᴀʀ **Rᴇᴘʟʏ** ᴋᴀʀᴋᴇ ʜɪ ᴄᴏᴍᴍᴀɴᴅ ᴜsᴇ ᴋᴀʀᴇɪɴ.
"""
