import os
import textwrap
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
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


# -------------------------------------------------------------------------
# LOCAL QUOTE GENERATOR (NO THIRD-PARTY API DEPENDENCY - 0% FAILURE)
# -------------------------------------------------------------------------

def draw_rounded_rect(draw, coords, radius, fill):
    x1, y1, x2, y2 = coords
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill)


def make_circular_avatar(im: Image.Image, size: int = 50) -> Image.Image:
    im = im.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(im, (0, 0), mask=mask)
    return output


async def generate_local_quote(messages: list) -> BytesIO:
    card_width = 512
    margin_x = 20
    content_width = card_width - (margin_x * 2)

    font_name = ImageFont.load_default()
    font_text = ImageFont.load_default()
    font_reply = ImageFont.load_default()

    items = []
    total_height = 20

    for msg in messages:
        sender_name = (
            f"{msg.from_user.first_name or ''} {msg.from_user.last_name or ''}".strip()
            if msg.from_user
            else (msg.sender_chat.title if msg.sender_chat else "User")
        )
        text = msg.text or msg.caption or "Sticker/Media"

        # Text wrapping
        wrapped_lines = textwrap.wrap(text, width=40)
        if not wrapped_lines:
            wrapped_lines = [""]

        reply_info = None
        if msg.reply_to_message and len(messages) == 1:
            rep = msg.reply_to_message
            rep_user = (
                f"{rep.from_user.first_name or ''} {rep.from_user.last_name or ''}".strip()
                if rep.from_user
                else "User"
            )
            rep_text = rep.text or rep.caption or "Media"
            rep_text = (rep_text[:30] + "...") if len(rep_text) > 30 else rep_text
            reply_info = {"user": rep_user, "text": rep_text}

        # Bubble calculation
        bubble_h = 30 + (len(wrapped_lines) * 16)
        if reply_info:
            bubble_h += 38

        items.append({
            "name": sender_name,
            "lines": wrapped_lines,
            "reply": reply_info,
            "bubble_h": bubble_h,
        })
        total_height += bubble_h + 15

    # Base Canvas
    img = Image.new("RGBA", (card_width, total_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    curr_y = 15
    for item in items:
        # Chat bubble background
        draw_rounded_rect(
            draw,
            (margin_x, curr_y, margin_x + content_width, curr_y + item["bubble_h"]),
            radius=16,
            fill=(27, 20, 41, 240),
        )

        # Name
        draw.text((margin_x + 15, curr_y + 8), item["name"], fill=(195, 140, 255), font=font_name)

        offset_y = curr_y + 26

        # Reply Quote box if present
        if item["reply"]:
            rx1 = margin_x + 15
            ry1 = offset_y
            rx2 = margin_x + content_width - 15
            ry2 = offset_y + 32

            draw_rounded_rect(draw, (rx1, ry1, rx2, ry2), radius=6, fill=(40, 30, 60))
            draw.rectangle([rx1, ry1, rx1 + 3, ry2], fill=(123, 91, 242))
            draw.text((rx1 + 8, ry1 + 3), item["reply"]["user"], fill=(160, 160, 255), font=font_reply)
            draw.text((rx1 + 8, ry1 + 16), item["reply"]["text"], fill=(200, 200, 200), font=font_reply)
            offset_y += 38

        # Message Text
        for line in item["lines"]:
            draw.text((margin_x + 15, offset_y), line, fill=(255, 255, 255), font=font_text)
            offset_y += 16

        curr_y += item["bubble_h"] + 15

    out = BytesIO()
    img.save(out, format="WEBP")
    out.name = "quote.webp"
    out.seek(0)
    return out


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

        # /q p ya /q r: Original parent message + replied message dono include honge
        if arg in ["p", "r"]:
            if target_msg.reply_to_message:
                messages = [target_msg.reply_to_message, target_msg]
            else:
                messages = [target_msg]
        elif arg.isdigit():
            count = max(1, min(int(arg), 10))
            msg_ids = list(range(target_msg.id, target_msg.id + count))
            fetched = await client.get_messages(chat_id=message.chat.id, message_ids=msg_ids)
            messages = [m for m in fetched if m and not m.empty]
        else:
            messages = [target_msg]

        quote_file = await generate_local_quote(messages)

        await message.reply_sticker(sticker=quote_file)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(
            f'<emoji id="{PREMIUM_EMOJI_RIGHT}">❌</emoji> **Eʀʀᴏʀ:**\n'
            f'> `{str(e)}`'
        )


# -------------------------------------------------------------------------
# KANG HANDLER (/kang) - Auto Pack Creator & Sticker Refresher
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

        # Telegram cache refresh sticker drop
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
