import os
import textwrap
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from pyrogram import filters, enums
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
# LOCAL QUOTE ENGINE (ZERO NETWORK DEPENDENCY - NO ERRNO -2)
# -------------------------------------------------------------------------

def clean_text(text: str) -> str:
    if not text:
        return ""
    return str(text).encode("utf-8", "ignore").decode("utf-8")


def get_system_font(size: int = 15, bold: bool = False):
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


async def render_quote_sticker(messages: list) -> BytesIO:
    card_width = 512
    margin_x = 18
    content_width = card_width - (margin_x * 2)

    font_name = get_system_font(16, bold=True)
    font_text = get_system_font(15, bold=False)
    font_reply = get_system_font(13, bold=False)

    parsed_items = []
    total_height = 20

    for msg in messages:
        sender = msg.from_user or msg.sender_chat
        name = clean_text(
            f"{sender.first_name or ''} {sender.last_name or ''}".strip()
            if hasattr(sender, "first_name")
            else (getattr(sender, "title", "") or "User")
        )
        text = clean_text(msg.text or msg.caption or "Sticker / Media")

        lines = textwrap.wrap(text, width=36)
        if not lines:
            lines = [""]

        reply_box = None
        if msg.reply_to_message and len(messages) == 1:
            rep = msg.reply_to_message
            rep_sender = rep.from_user or rep.sender_chat
            r_name = clean_text(
                f"{rep_sender.first_name or ''} {rep_sender.last_name or ''}".strip()
                if hasattr(rep_sender, "first_name")
                else (getattr(rep_sender, "title", "") or "User")
            )
            r_text = clean_text(rep.text or rep.caption or "Media")
            if len(r_text) > 30:
                r_text = r_text[:30] + "..."
            reply_box = {"name": r_name, "text": r_text}

        bubble_h = 36 + (len(lines) * 20)
        if reply_box:
            bubble_h += 44

        parsed_items.append({
            "name": name,
            "lines": lines,
            "reply": reply_box,
            "height": bubble_h,
        })
        total_height += bubble_h + 16

    # Image background
    img = Image.new("RGBA", (card_width, total_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    curr_y = 15
    for item in parsed_items:
        x1 = margin_x
        y1 = curr_y
        x2 = margin_x + content_width
        y2 = curr_y + item["height"]

        # Main Chat Bubble
        draw.rounded_rectangle([x1, y1, x2, y2], radius=18, fill=(27, 20, 41, 250))

        # Sender Name
        draw.text((x1 + 18, y1 + 10), item["name"], fill=(195, 140, 255), font=font_name)

        offset_y = y1 + 34

        # Reply Quote Box
        if item["reply"]:
            rx1 = x1 + 18
            ry1 = offset_y
            rx2 = x2 - 18
            ry2 = offset_y + 38

            draw.rounded_rectangle([rx1, ry1, rx2, ry2], radius=8, fill=(42, 31, 64))
            draw.rectangle([rx1, ry1, rx1 + 4, ry2], fill=(123, 91, 242))
            draw.text((rx1 + 10, ry1 + 4), item["reply"]["name"], fill=(160, 160, 255), font=font_reply)
            draw.text((rx1 + 10, ry1 + 20), item["reply"]["text"], fill=(210, 210, 210), font=font_reply)
            offset_y += 46

        # Message Text Lines
        for line in item["lines"]:
            draw.text((x1 + 18, offset_y), line, fill=(255, 255, 255), font=font_text)
            offset_y += 20

        curr_y += item["height"] + 16

    out = BytesIO()
    img.save(out, format="WEBP")
    out.name = "quote.webp"
    out.seek(0)
    return out


# -------------------------------------------------------------------------
# QUOTE COMMAND (/q, /q p, /q r)
# -------------------------------------------------------------------------

@app.on_message(filters.command(["q", "quote"]) & filters.reply)
async def quotly_command(client: app, message: Message):
    status_msg = await message.reply_text(
        f'<emoji id="{PREMIUM_EMOJI_LEFT}">⚡</emoji> <b>Gᴇɴᴇʀᴀᴛɪɴɢ Qᴜᴏᴛᴇ...</b>',
        parse_mode=enums.ParseMode.HTML,
    )

    try:
        args = message.text.split()[1:] if message.text else []
        arg = args[0].lower() if args else ""
        target_msg = message.reply_to_message

        # /q p ya /q r: Dono users ka separate chat bubble
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

        sticker_file = await render_quote_sticker(messages)

        await message.reply_sticker(sticker=sticker_file)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(
            f'<emoji id="{PREMIUM_EMOJI_RIGHT}">❌</emoji> <b>Eʀʀᴏʀ:</b>\n'
            f'<blockquote><code>{str(e)}</code></blockquote>',
            parse_mode=enums.ParseMode.HTML,
        )


# -------------------------------------------------------------------------
# KANG COMMAND (/kang)
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
            f'<emoji id="{PREMIUM_EMOJI_RIGHT}">❌</emoji> <b>Kʀɪᴘʏᴀ ᴋɪsɪ ᴘʜᴏᴛᴏ, sᴛɪᴄᴋᴇʀ ʏᴀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴘᴀʀ ʀᴇᴘʟʏ ᴋᴀʀᴇɪɴ.</b>',
            parse_mode=enums.ParseMode.HTML,
        )

    status_msg = await message.reply_text(
        f'<emoji id="{PREMIUM_EMOJI_LEFT}">⚡</emoji> <b>Pʀᴏᴄᴇssɪɴɢ Sᴛɪᴄᴋᴇʀ...</b>',
        parse_mode=enums.ParseMode.HTML,
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
        stickers_count = 1
        short_name = ""
        pack_title = ""

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
                stickers_count = sticker_set.set.count + 1
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
                stickers_count = 1
                pack_created = True

        pack_url = f"https://t.me/addstickers/{short_name}"
        button = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Oᴘᴇɴ Pᴀᴄᴋ", url=pack_url)]]
        )

        caption_text = (
            f'<emoji id="{PREMIUM_EMOJI_LEFT}">✨</emoji> <b>Kᴀɴɢᴇᴅ.</b>\n\n'
            f'<blockquote>'
            f'<b>Pᴀᴄᴋ:</b> <code>{pack_title}</code>\n'
            f'<b>Tʏᴘᴇ:</b> <code>ʀᴇɢᴜʟᴀʀ</code>\n'
            f'<b>Sᴛɪᴄᴋᴇʀs:</b> <code>{stickers_count}</code>\n'
            f'<b>Eᴍᴏᴊɪ:</b> {sticker_emoji}'
            f'</blockquote>'
        )

        await status_msg.edit_text(
            caption_text,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=button,
        )

        sticker_data.seek(0)
        await message.reply_sticker(sticker=sticker_data)

    except Exception as e:
        await status_msg.edit_text(
            f'<emoji id="{PREMIUM_EMOJI_RIGHT}">❌</emoji> <b>Eʀʀᴏʀ:</b>\n'
            f'<blockquote><code>{str(e)}</code></blockquote>',
            parse_mode=enums.ParseMode.HTML,
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# -------------------------------------------------------------------------
# MODULE & HELP INFO
# -------------------------------------------------------------------------

__MODULE__ = "Qᴜᴏᴛᴇ"

__HELP__ = """
<b>Qᴜᴏᴛᴇ & Sᴛɪᴄᴋᴇʀ Mᴏᴅᴜʟᴇ</b>

<b>Qᴜᴏᴛᴇ Cᴏᴍᴍᴀɴᴅs:</b>
<blockquote>
• <code>/q</code> : Qᴜᴏᴛᴇ ᴀ sɪɴɢʟᴇ ᴍᴇssᴀɢᴇ.
• <code>/q p</code> ᴏʀ <code>/q r</code> : Qᴜᴏᴛᴇ ʀᴇᴘʟɪᴇᴅ ᴍᴇssᴀɢᴇ ᴡɪᴛʜ ɪᴛs ᴘᴀʀᴇɴᴛ ᴍᴇssᴀɢᴇ.
• <code>/q [1-10]</code> : Qᴜᴏᴛᴇ ᴍᴜʟᴛɪᴘʟᴇ ᴍᴇssᴀɢᴇs ᴀᴛ ᴏɴᴄᴇ (ᴇ.ɢ. <code>/q 3</code>).
</blockquote>

<b>Sᴛɪᴄᴋᴇʀ Kᴀɴɢ Cᴏᴍᴍᴀɴᴅs:</b>
<blockquote>
• <code>/kang</code> : Kᴀɴɢ sᴛɪᴄᴋᴇʀ, ᴘʜᴏᴛᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ʏᴏᴜʀ ᴘᴇʀsᴏɴᴀʟ ᴘᴀᴄᴋ.
• <code>/kang [emoji]</code> : Kᴀɴɢ ᴡɪᴛʜ ʏᴏᴜʀ ᴄᴜsᴛᴏᴍ ᴇᴍᴏᴊɪ (ᴇ.ɢ. <code>/kang 🔥</code>).
</blockquote>

<b>Nᴏᴛᴇ:</b>
<blockquote>• Hᴀᴍᴇsʜᴀ ᴛᴀʀɢᴇᴛ ᴍᴇssᴀɢᴇ ʏᴀ ᴍᴇᴅɪᴀ ᴘᴀʀ <b>Rᴇᴘʟʏ</b> ᴋᴀʀᴋᴇ ʜɪ ᴄᴏᴍᴍᴀɴᴅ ᴜsᴇ ᴋᴀʀᴇɪɴ.</blockquote>
"""
