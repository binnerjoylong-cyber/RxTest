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

# Configured Custom Emojis & Premium Palette
PRIMARY_BG_COLOR = "#141318"
ACCENT_COLOR = "#7b5bf2"
PREMIUM_EMOJI_LEFT = "5895221391220804630"
PREMIUM_EMOJI_RIGHT = "5895648298085125845"

fetch = AsyncClient(
    http2=True,
    verify=False,
    headers={
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    },
    timeout=Timeout(25),
)


class QuotlyException(Exception):
    pass


# -------------------------------------------------------------------------
# QUOTLY HELPERS
# -------------------------------------------------------------------------

async def get_message_sender_id(ctx: Message) -> int:
    if ctx.forward_date:
        if ctx.forward_from:
            return ctx.forward_from.id
        elif ctx.forward_from_chat:
            return ctx.forward_from_chat.id
        return 1
    if ctx.from_user:
        return ctx.from_user.id
    if ctx.sender_chat:
        return ctx.sender_chat.id
    return 1


async def get_message_sender_name(ctx: Message) -> str:
    if ctx.forward_date:
        if ctx.forward_sender_name:
            return ctx.forward_sender_name
        if ctx.forward_from:
            return f"{ctx.forward_from.first_name or ''} {ctx.forward_from.last_name or ''}".strip()
        if ctx.forward_from_chat:
            return ctx.forward_from_chat.title or "Channel"
        return "Unknown"
    if ctx.from_user:
        return f"{ctx.from_user.first_name or ''} {ctx.from_user.last_name or ''}".strip()
    if ctx.sender_chat:
        return ctx.sender_chat.title or "Channel"
    return "Unknown"


async def get_message_sender_username(ctx: Message) -> str:
    if ctx.forward_date:
        if ctx.forward_from and ctx.forward_from.username:
            return ctx.forward_from.username
        if ctx.forward_from_chat and ctx.forward_from_chat.username:
            return ctx.forward_from_chat.username
        return ""
    if ctx.from_user and ctx.from_user.username:
        return ctx.from_user.username
    if ctx.sender_chat and ctx.sender_chat.username:
        return ctx.sender_chat.username
    return ""


async def get_text_or_caption(ctx: Message) -> str:
    return ctx.text or ctx.caption or ""


async def get_custom_emoji_id(ctx: Message) -> str:
    if ctx.from_user and ctx.from_user.emoji_status:
        return str(ctx.from_user.emoji_status.custom_emoji_id)
    return PREMIUM_EMOJI_LEFT


async def pyrogram_to_quotly(messages: list, is_reply: bool = False):
    payload = {
        "type": "quote",
        "format": "webp",
        "backgroundColor": PRIMARY_BG_COLOR,
        "messages": [],
    }

    for msg in messages:
        entities = []
        raw_entities = msg.entities or msg.caption_entities
        if raw_entities:
            for ent in raw_entities:
                item = {
                    "type": ent.type.name.lower(),
                    "offset": ent.offset,
                    "length": ent.length,
                }
                if hasattr(ent, "custom_emoji_id") and ent.custom_emoji_id:
                    item["customEmojiId"] = str(ent.custom_emoji_id)
                entities.append(item)

        custom_status = await get_custom_emoji_id(msg)

        msg_data = {
            "entities": entities,
            "chatId": await get_message_sender_id(msg),
            "text": await get_text_or_caption(msg),
            "avatar": True,
            "emojiStatus": custom_status,
            "from": {
                "id": await get_message_sender_id(msg),
                "name": await get_message_sender_name(msg),
                "username": await get_message_sender_username(msg),
                "type": msg.chat.type.name.lower() if msg.chat else "supergroup",
                "color": ACCENT_COLOR,
            },
        }

        if is_reply and msg.reply_to_message:
            rep = msg.reply_to_message
            msg_data["replyMessage"] = {
                "name": await get_message_sender_name(rep),
                "text": await get_text_or_caption(rep),
                "chatId": await get_message_sender_id(rep),
            }

        payload["messages"].append(msg_data)

    r = await fetch.post("https://bot.lyo.su/quote/generate", json=payload)
    if r.status_code == 200:
        return r.read()
    else:
        try:
            err = r.json().get("message", r.text)
        except Exception:
            err = f"API Error (HTTP {r.status_code})"
        raise QuotlyException(err)


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

        if arg in ["p", "r"]:
            target_msg = message.reply_to_message
            if target_msg.reply_to_message:
                messages = [target_msg.reply_to_message, target_msg]
            else:
                messages = [target_msg]
            is_reply = False
        elif arg.isdigit():
            count = max(1, min(int(arg), 10))
            msg_ids = list(range(message.reply_to_message.id, message.reply_to_message.id + count))
            fetched = await client.get_messages(chat_id=message.chat.id, message_ids=msg_ids)
            messages = [m for m in fetched if m and not m.empty]
            is_reply = False
        else:
            messages = [message.reply_to_message]
            is_reply = bool(message.reply_to_message.reply_to_message)

        quote_bytes = await pyrogram_to_quotly(messages, is_reply=is_reply)

        sticker_file = BytesIO(quote_bytes)
        sticker_file.name = "quote.webp"

        await message.reply_sticker(sticker=sticker_file)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(
            f'<emoji id="{PREMIUM_EMOJI_RIGHT}">❌</emoji> **Eʀʀᴏʀ:**\n`{str(e)}`'
        )


# -------------------------------------------------------------------------
# KANG HANDLER (/kang) - Auto Pack Creator & Sticker Adder
# -------------------------------------------------------------------------

async def convert_to_valid_sticker(image_path: str) -> BytesIO:
    im = Image.open(image_path)
    im.thumbnail((512, 512), Image.Resampling.LANCZOS)
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
            pack_title = f"{user.first_name}'s Kang Static #{pack_num}"

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
            f'<emoji id="{PREMIUM_EMOJI_LEFT}">✨</emoji> **Kᴀɴɢᴇᴅ Sᴜᴄᴄᴇssғᴜʟʟʏ!**\n\n'
            f'**Pᴀᴄᴋ:** `{pack_title}`\n'
            f'**Eᴍᴏᴊɪ:** {sticker_emoji}\n'
            f'**Tʏᴘᴇ:** Rᴇɢᴜʟᴀʀ',
            reply_markup=button,
        )

    except Exception as e:
        await status_msg.edit_text(
            f'<emoji id="{PREMIUM_EMOJI_RIGHT}">❌</emoji> **Eʀʀᴏʀ:**\n`{str(e)}`'
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
• `/q` : Qᴜᴏᴛᴇ ᴀ sɪɴɢʟᴇ ᴍᴇssᴀɢᴇ.
• `/q p` ᴏʀ `/q r` : Qᴜᴏᴛᴇ ʀᴇᴘʟɪᴇᴅ ᴍᴇssᴀɢᴇ ᴡɪᴛʜ ɪᴛs ᴘᴀʀᴇɴᴛ ᴍᴇssᴀɢᴇ.
• `/q [1-10]` : Qᴜᴏᴛᴇ ᴍᴜʟᴛɪᴘʟᴇ ᴍᴇssᴀɢᴇs ᴀᴛ ᴏɴᴄᴇ (ᴇ.ɢ. `/q 3`).

**Sᴛɪᴄᴋᴇʀ Kᴀɴɢ Cᴏᴍᴍᴀɴᴅs:**
• `/kang` : Kᴀɴɢ sᴛɪᴄᴋᴇʀ, ᴘʜᴏᴛᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ʏᴏᴜʀ ᴘᴇʀsᴏɴᴀʟ ᴘᴀᴄᴋ.
• `/kang [emoji]` : Kᴀɴɢ ᴡɪᴛʜ ʏᴏᴜʀ ᴄᴜsᴛᴏᴍ ᴇᴍᴏᴊɪ (ᴇ.ɢ. `/kang 🔥`).

**Nᴏᴛᴇ:**
• Hᴀᴍᴇsʜᴀ ᴛᴀʀɢᴇᴛ ᴍᴇssᴀɢᴇ ʏᴀ ᴍᴇᴅɪᴀ ᴘᴀʀ **Rᴇᴘʟʏ** ᴋᴀʀᴋᴇ ʜɪ ᴄᴏᴍᴍᴀɴᴅ ᴜsᴇ ᴋᴀʀᴇɪɴ.
"""
