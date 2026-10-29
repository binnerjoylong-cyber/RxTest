import os
import re
import textwrap
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
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

http_client = AsyncClient(
    http2=False,
    verify=False,
    headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    },
    timeout=Timeout(25),
)


# -------------------------------------------------------------------------
# UTF-8 SAFE FALLBACK QUOTE GENERATOR
# -------------------------------------------------------------------------

def sanitize_text(text: str) -> str:
    """Non-ASCII characters ko safe string me badalta hai taaki Pillow crash na kare"""
    if not text:
        return ""
    # Safe unicode cleaning
    return text.encode("utf-8", "ignore").decode("utf-8")


def draw_rounded_rect(draw, coords, radius, fill):
    draw.rounded_rectangle(coords, radius=radius, fill=fill)


async def generate_local_quote(messages: list) -> BytesIO:
    card_width = 512
    margin_x = 20
    content_width = card_width - (margin_x * 2)

    try:
        # Standard system font use karein jo Unicode handle kare
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
    except Exception:
        font = ImageFont.load_default()
        font_bold = font

    items = []
    total_height = 20

    for msg in messages:
        sender_name = sanitize_text(
            f"{msg.from_user.first_name or ''} {msg.from_user.last_name or ''}".strip()
            if msg.from_user
            else (msg.sender_chat.title if msg.sender_chat else "User")
        )
        raw_text = sanitize_text(msg.text or msg.caption or "Media")

        wrapped_lines = textwrap.wrap(raw_text, width=38)
        if not wrapped_lines:
            wrapped_lines = [""]

        reply_info = None
        if msg.reply_to_message and len(messages) == 1:
            rep = msg.reply_to_message
            rep_user = sanitize_text(
                f"{rep.from_user.first_name or ''} {rep.from_user.last_name or ''}".strip()
                if rep.from_user
                else "User"
            )
            rep_text = sanitize_text(rep.text or rep.caption or "Media")
            rep_text = (rep_text[:28] + "...") if len(rep_text) > 28 else rep_text
            reply_info = {"user": rep_user, "text": rep_text}

        bubble_h = 32 + (len(wrapped_lines) * 18)
        if reply_info:
            bubble_h += 42

        items.append({
            "name": sender_name,
            "lines": wrapped_lines,
            "reply": reply_info,
            "bubble_h": bubble_h,
        })
        total_height += bubble_h + 15

    img = Image.new("RGBA", (card_width, total_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    curr_y = 15
    for item in items:
        # Bubble Box
        draw_rounded_rect(
            draw,
            (margin_x, curr_y, margin_x + content_width, curr_y + item["bubble_h"]),
            radius=16,
            fill=(27, 20, 41, 245),
        )

        # Sender Name
        draw.text((margin_x + 15, curr_y + 8), item["name"], fill=(195, 140, 255), font=font_bold)

        offset_y = curr_y + 30

        if item["reply"]:
            rx1 = margin_x + 15
            ry1 = offset_y
            rx2 = margin_x + content_width - 15
            ry2 = offset_y + 36

            draw_rounded_rect(draw, (rx1, ry1, rx2, ry2), radius=6, fill=(45, 33, 68))
            draw.rectangle([rx1, ry1, rx1 + 3, ry2], fill=(123, 91, 242))
            draw.text((rx1 + 8, ry1 + 3), item["reply"]["user"], fill=(160, 160, 255), font=font)
            draw.text((rx1 + 8, ry1 + 18), item["reply"]["text"], fill=(210, 210, 210), font=font)
            offset_y += 42

        for line in item["lines"]:
            draw.text((margin_x + 15, offset_y), line, fill=(255, 255, 255), font=font)
            offset_y += 18

        curr_y += item["bubble_h"] + 15

    out = BytesIO()
    img.save(out, format="WEBP")
    out.name = "quote.webp"
    out.seek(0)
    return out


# -------------------------------------------------------------------------
# QUOTLY API HANDLER
# -------------------------------------------------------------------------

async def fetch_quotly_api(messages: list, is_reply: bool = False):
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
                entities.append({
                    "type": ent.type.name.lower(),
                    "offset": ent.offset,
                    "length": ent.length,
                })

        sender_id = msg.from_user.id if msg.from_user else (msg.sender_chat.id if msg.sender_chat else 1)
        sender_name = (
            f"{msg.from_user.first_name or ''} {msg.from_user.last_name or ''}".strip()
            if msg.from_user
            else (msg.sender_chat.title if msg.sender_chat else "User")
        )
        sender_username = (
            msg.from_user.username
            if msg.from_user and msg.from_user.username
            else (msg.sender_chat.username if msg.sender_chat and msg.sender_chat.username else "")
        )

        msg_data = {
            "entities": entities,
            "chatId": sender_id,
            "text": msg.text or msg.caption or "",
            "avatar": True,
            "from": {
                "id": sender_id,
                "name": sender_name,
                "username": sender_username,
                "type": msg.chat.type.name.lower() if msg.chat else "supergroup",
                "color": ACCENT_COLOR,
            },
        }

        if is_reply and msg.reply_to_message:
            rep = msg.reply_to_message
            rep_name = (
                f"{rep.from_user.first_name or ''} {rep.from_user.last_name or ''}".strip()
                if rep.from_user
                else "User"
            )
            msg_data["replyMessage"] = {
                "name": rep_name,
                "text": rep.text or rep.caption or "",
                "chatId": rep.from_user.id if rep.from_user else 1,
            }

        payload["messages"].append(msg_data)

    # Online API primary call
    endpoints = [
        "https://bot.lyo.su/quote/generate",
        "https://quote.chaotic.ninja/generate",
    ]

    for url in endpoints:
        try:
            res = await http_client.post(url, json=payload)
            if res.status_code == 200 and res.content:
                out = BytesIO(res.content)
                out.name = "quote.webp"
                out.seek(0)
                return out
        except Exception:
            continue

    # Agar API fail ho jaye toh safe local image generator run hoga
    return await generate_local_quote(messages)


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

        # /q p ya /q r
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

        sticker_file = await fetch_quotly_api(messages, is_reply=is_reply)

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
    if width >= height:
        new_width = 512
        new_height = max(1, int((512 / width) * height))
    else:
        new_height = 512
        new_width = max(1, int((512 / height) * width))

    im = im.resize((new_width, new_height), Image.Resampling.LANCZOS)
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

        user_peer = await client.resolve_peer(user.id)

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
                        user_id=user_peer,
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

        sticker_data.seek(0)
        await message.reply_sticker(sticker=sticker_data)

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
