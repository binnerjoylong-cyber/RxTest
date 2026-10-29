import os
from io import BytesIO
from PIL import Image
from httpx import AsyncClient, Timeout
from pyrogram import filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import StickersetInvalid, PeerIdInvalid
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
    timeout=Timeout(30),
)


class QuotlyException(Exception):
    pass


# -------------------------------------------------------------------------
# QUOTLY PAYLOAD BUILDER
# -------------------------------------------------------------------------

def get_name(user) -> str:
    if not user:
        return "Unknown"
    first = getattr(user, "first_name", "") or getattr(user, "title", "")
    last = getattr(user, "last_name", "") or ""
    return f"{first} {last}".strip() or "User"


def get_username(user) -> str:
    if not user:
        return ""
    return getattr(user, "username", "") or ""


async def parse_entities(msg: Message) -> list:
    entities = []
    raw_ents = msg.entities or msg.caption_entities
    if raw_ents:
        for ent in raw_ents:
            ent_type = ent.type.name.lower() if hasattr(ent.type, "name") else str(ent.type).lower()
            item = {
                "type": ent_type,
                "offset": ent.offset,
                "length": ent.length,
            }
            if hasattr(ent, "custom_emoji_id") and ent.custom_emoji_id:
                item["customEmojiId"] = str(ent.custom_emoji_id)
            entities.append(item)
    return entities


async def build_quotly_msg(msg: Message) -> dict:
    sender = msg.from_user or msg.sender_chat
    sender_id = sender.id if sender else 1
    sender_name = get_name(sender)
    sender_username = get_username(sender)

    msg_dict = {
        "entities": await parse_entities(msg),
        "chatId": sender_id,
        "text": msg.text or msg.caption or "",
        "avatar": True,
        "from": {
            "id": sender_id,
            "name": sender_name,
            "username": sender_username,
            "type": "user",
            "color": ACCENT_COLOR,
        },
    }

    if msg.from_user and msg.from_user.emoji_status:
        msg_dict["emojiStatus"] = str(msg.from_user.emoji_status.custom_emoji_id)

    return msg_dict


async def pyrogram_to_quotly(messages: list, is_reply: bool = False) -> BytesIO:
    payload = {
        "type": "quote",
        "format": "webp",
        "backgroundColor": PRIMARY_BG_COLOR,
        "messages": [],
    }

    for msg in messages:
        msg_dict = await build_quotly_msg(msg)

        if is_reply and msg.reply_to_message:
            rep = msg.reply_to_message
            rep_sender = rep.from_user or rep.sender_chat
            msg_dict["replyMessage"] = {
                "name": get_name(rep_sender),
                "text": rep.text or rep.caption or "Media",
                "chatId": rep_sender.id if rep_sender else 1,
            }

        payload["messages"].append(msg_dict)

    endpoints = [
        "https://bot.lyo.su/quote/generate",
        "https://quote.chaotic.ninja/generate",
    ]

    last_err = ""
    for url in endpoints:
        try:
            res = await http_client.post(url, json=payload)
            if res.status_code == 200 and res.content:
                out = BytesIO(res.content)
                out.name = "quote.webp"
                out.seek(0)
                return out
            last_err = f"HTTP {res.status_code}"
        except Exception as e:
            last_err = str(e)
            continue

    raise QuotlyException(last_err or "Quotly server offline")


# -------------------------------------------------------------------------
# QUOTE HANDLER (/q, /q p, /q r)
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

        # /q p ya /q r: Dono users ka conversation bubble
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
            f'<emoji id="{PREMIUM_EMOJI_RIGHT}">❌</emoji> <b>Eʀʀᴏʀ:</b>\n'
            f'<blockquote><code>{str(e)}</code></blockquote>',
            parse_mode=enums.ParseMode.HTML,
        )


# -------------------------------------------------------------------------
# KANG HANDLER (/kang) - Auto Pack Append (120 Limit per pack)
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

                # Add to existing pack
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
                # Create brand new set
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

        # Send sticker to chat so Telegram immediately refreshes the set preview
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
