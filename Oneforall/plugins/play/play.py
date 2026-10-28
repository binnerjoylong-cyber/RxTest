import inspect
import math
import random
import re
import string
from typing import Dict, List, Union

from pyrogram import enums, filters, types
from pyrogram.types import Message
from pytgcalls.exceptions import NoActiveGroupCall
from youtube_search import YoutubeSearch

import config
from config import BANNED_USERS, lyrical
from Oneforall import Apple, Resso, SoundCloud, Spotify, Telegram, YouTube, app
from Oneforall.core.call import (
    DIVERSE_POOLS,
    Hotty,
    _clean_track_title,
    build_suggestion_blocks,
    fetch_random_diverse_tracks,
    suggestion_cache,
)
from Oneforall.core.mongo import mongodb
from Oneforall.utils import seconds_to_min, time_to_seconds
from Oneforall.utils.channelplay import get_channeplayCB
from Oneforall.utils.database import add_active_video_chat, remove_active_video_chat
from Oneforall.utils.decorators.language import languageCB
from Oneforall.utils.decorators.play import PlayWrapper
from Oneforall.utils.formatters import formats
from Oneforall.utils.inline import (
    botplaylist_markup,
    livestream_markup,
    playlist_markup,
    slider_markup,
    track_markup,
)
from Oneforall.utils.inline.rich import (
    caption_blocks,
    deliver_rich,
    edit_rich,
    html_to_rich_blocks,
)
from Oneforall.utils.logger import play_logs
from Oneforall.utils.stream.stream import stream

playlistdb = mongodb.playlist
PAGE_SIZE = 7


async def _call_db_func(func, *args, **kwargs):
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    res = func(*args, **kwargs)
    if inspect.isawaitable(res):
        return await res
    return res


async def _get_playlists(chat_id: int) -> Dict[str, dict]:
    _notes = await playlistdb.find_one({"chat_id": chat_id})
    if not _notes:
        return {}
    return _notes.get("notes", {})


async def get_playlist_names(chat_id: int) -> List[str]:
    notes = await _get_playlists(chat_id)
    return list(notes.keys())


async def get_playlist(chat_id: int, name: str) -> Union[bool, dict]:
    _notes = await _get_playlists(chat_id)
    return _notes.get(name, False)


async def get_rich_see_page(user_id: int, page: int = 0):
    all_tracks = await get_playlist_names(user_id)
    total_tracks = len(all_tracks)
    if total_tracks == 0:
        return [], 0, 0

    total_pages = math.ceil(total_tracks / PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    current_batch = all_tracks[start:end]

    blocks = []
    for idx, x in enumerate(current_batch, start=start + 1):
        _note = await get_playlist(user_id, x)
        title = _note["title"].title() if (_note and isinstance(_note, dict) and "title" in _note) else str(x)
        blocks.append(
            types.InputRichBlockButtons(
                buttons=[
                    types.RichMessageButton(
                        text=f"▶️ {idx}. {title[:28]}",
                        style=enums.ButtonStyle.SUCCESS,
                        callback_data=f"play_from_here|{user_id}|{x}",
                    )
                ]
            )
        )

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            types.RichMessageButton(
                text="⬅️ Back",
                style=enums.ButtonStyle.DEFAULT,
                callback_data=f"see_page|{user_id}|{page - 1}",
            )
        )
    nav_buttons.append(
        types.RichMessageButton(
            text=f"📄 {page + 1}/{total_pages}",
            style=enums.ButtonStyle.DEFAULT,
            callback_data="see_page_indicator",
        )
    )
    if page < total_pages - 1:
        nav_buttons.append(
            types.RichMessageButton(
                text="Next ➡️",
                style=enums.ButtonStyle.DEFAULT,
                callback_data=f"see_page|{user_id}|{page + 1}",
            )
        )
    blocks.append(types.InputRichBlockButtons(buttons=nav_buttons))

    blocks.append(
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text="🔀 Shuffle",
                    style=enums.ButtonStyle.PRIMARY,
                    callback_data=f"stream_user_plist|a|{user_id}|shuffle",
                ),
                types.RichMessageButton(
                    text="✖ Close",
                    style=enums.ButtonStyle.DANGER,
                    callback_data="close",
                ),
            ]
        )
    )
    return blocks, total_tracks, total_pages


async def send_rich_block(chat_id: int, text: str, rich_buttons: list = None, img_url: str = None):
    blocks = caption_blocks(text)
    if rich_buttons:
        blocks.extend(rich_buttons)
    return await deliver_rich(app, chat_id, blocks)


async def _safe_edit_err(mystic, message, err):
    try:
        return await mystic.edit_text(str(err))
    except Exception:
        try:
            return await message.reply_text(str(err))
        except Exception:
            return


@app.on_message(
    filters.command(
        [
            "play",
            "vplay",
            "cplay",
            "cvplay",
            "playforce",
            "vplayforce",
            "cplayforce",
            "cvplayforce",
        ]
    )
    & filters.group
    & ~BANNED_USERS
)
@PlayWrapper
async def play_commnd(
    client,
    message: Message,
    _,
    chat_id,
    video,
    channel,
    playmode,
    url,
    fplay,
):
    mystic = await message.reply_text(
        _["play_2"].format(channel) if channel else _["play_1"]
    )
    plist_id = None
    slider = None
    plist_type = None
    spotify = None
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    audio_telegram = (
        (message.reply_to_message.audio or message.reply_to_message.voice)
        if message.reply_to_message
        else None
    )
    video_telegram = (
        (message.reply_to_message.video or message.reply_to_message.document)
        if message.reply_to_message
        else None
    )
    if audio_telegram:
        if audio_telegram.file_size > 104857600:
            return await _safe_edit_err(mystic, message, _["play_5"])
        duration_min = seconds_to_min(audio_telegram.duration)
        if (audio_telegram.duration) > config.DURATION_LIMIT:
            return await _safe_edit_err(
                mystic, message, _["play_6"].format(config.DURATION_LIMIT_MIN, app.mention)
            )
        file_path = await Telegram.get_filepath(audio=audio_telegram)
        if not file_path:
            return await _safe_edit_err(mystic, message, "Download failed or stream URL not found.")
        if await Telegram.download(_, message, mystic, file_path):
            message_link = await Telegram.get_link(message)
            file_name = await Telegram.get_filename(audio_telegram, audio=True)
            dur = await Telegram.get_duration(audio_telegram, file_path)
            details = {
                "title": file_name,
                "link": message_link,
                "path": file_path,
                "dur": dur,
            }

            try:
                await stream(
                    _,
                    mystic,
                    user_id,
                    details,
                    chat_id,
                    user_name,
                    message.chat.id,
                    streamtype="telegram",
                    forceplay=fplay,
                )
            except Exception as e:
                ex_type = type(e).__name__
                err = e if ex_type == "AssistantErr" else f"{ex_type}: {e}"
                return await _safe_edit_err(mystic, message, err)
            return
        return
    elif video_telegram:
        if message.reply_to_message.document:
            try:
                ext = video_telegram.file_name.split(".")[-1]
                if ext.lower() not in formats:
                    return await _safe_edit_err(
                        mystic, message, _["play_7"].format(f"{' | '.join(formats)}")
                    )
            except Exception:
                return await _safe_edit_err(
                    mystic, message, _["play_7"].format(f"{' | '.join(formats)}")
                )
        if video_telegram.file_size > config.TG_VIDEO_FILESIZE_LIMIT:
            return await _safe_edit_err(mystic, message, _["play_8"])
        file_path = await Telegram.get_filepath(video=video_telegram)
        if not file_path:
            return await _safe_edit_err(mystic, message, "Download failed or stream URL not found.")
        if await Telegram.download(_, message, mystic, file_path):
            message_link = await Telegram.get_link(message)
            file_name = await Telegram.get_filename(video_telegram)
            dur = await Telegram.get_duration(video_telegram, file_path)
            details = {
                "title": file_name,
                "link": message_link,
                "path": file_path,
                "dur": dur,
            }
            try:
                await stream(
                    _,
                    mystic,
                    user_id,
                    details,
                    chat_id,
                    user_name,
                    message.chat.id,
                    video=True,
                    streamtype="telegram",
                    forceplay=fplay,
                )
            except Exception as e:
                ex_type = type(e).__name__
                err = e if ex_type == "AssistantErr" else f"{ex_type}: {e}"
                return await _safe_edit_err(mystic, message, err)
            return
        return
    elif url:
        if await YouTube.exists(url):
            if "playlist" in url:
                try:
                    details = await YouTube.playlist(
                        url,
                        config.PLAYLIST_FETCH_LIMIT,
                        message.from_user.id,
                    )
                except Exception:
                    return await _safe_edit_err(mystic, message, _["play_3"])
                streamtype = "playlist"
                plist_type = "yt"
                if "&" in url:
                    plist_id = (url.split("=")[1]).split("&")[0]
                else:
                    plist_id = url.split("=")[1]
                img = config.PLAYLIST_IMG_URL
                cap = _["play_9"]
            else:
                try:
                    details, track_id = await YouTube.track(url)
                except Exception:
                    return await _safe_edit_err(mystic, message, _["play_3"])
                streamtype = "youtube"
                img = details["thumb"]
                cap = _["play_10"].format(
                    details["title"],
                    details["duration_min"],
                )
        elif await Spotify.valid(url):
            spotify = True
            if not config.SPOTIFY_CLIENT_ID and not config.SPOTIFY_CLIENT_SECRET:
                return await _safe_edit_err(
                    mystic, message, "» sᴘᴏᴛɪғʏ ɪs ɴᴏᴛ sᴜᴘᴘᴏʀᴛᴇᴅ ʏᴇᴛ.\n\nᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ."
                )
            if "track" in url:
                try:
                    details, track_id = await Spotify.track(url)
                except Exception:
                    return await _safe_edit_err(mystic, message, _["play_3"])
                streamtype = "youtube"
                img = details["thumb"]
                cap = _["play_10"].format(details["title"], details["duration_min"])
            elif "playlist" in url:
                try:
                    details, plist_id = await Spotify.playlist(url)
                except Exception:
                    return await _safe_edit_err(mystic, message, _["play_3"])
                streamtype = "playlist"
                plist_type = "spplay"
                img = config.SPOTIFY_PLAYLIST_IMG_URL
                cap = _["play_11"].format(app.mention, message.from_user.mention)
            elif "album" in url:
                try:
                    details, plist_id = await Spotify.album(url)
                except Exception:
                    return await _safe_edit_err(mystic, message, _["play_3"])
                streamtype = "playlist"
                plist_type = "spalbum"
                img = config.SPOTIFY_ALBUM_IMG_URL
                cap = _["play_11"].format(app.mention, message.from_user.mention)
            elif "artist" in url:
                try:
                    details, plist_id = await Spotify.artist(url)
                except Exception:
                    return await _safe_edit_err(mystic, message, _["play_3"])
                streamtype = "playlist"
                plist_type = "spartist"
                img = config.SPOTIFY_ARTIST_IMG_URL
                cap = _["play_11"].format(message.from_user.first_name)
            else:
                return await _safe_edit_err(mystic, message, _["play_15"])
        elif await Apple.valid(url):
            if "album" in url:
                try:
                    details, track_id = await Apple.track(url)
                except Exception:
                    return await _safe_edit_err(mystic, message, _["play_3"])
                streamtype = "youtube"
                img = details["thumb"]
                cap = _["play_10"].format(details["title"], details["duration_min"])
            elif "playlist" in url:
                spotify = True
                try:
                    details, plist_id = await Apple.playlist(url, True)
                except Exception:
                    return await _safe_edit_err(mystic, message, _["play_3"])
                streamtype = "playlist"
                plist_type = "apple"
                cap = _["play_12"].format(app.mention, message.from_user.mention)
                img = url
            else:
                return await _safe_edit_err(mystic, message, _["play_3"])
        elif await Resso.valid(url):
            try:
                details, track_id = await Resso.track(url)
            except Exception:
                return await _safe_edit_err(mystic, message, _["play_3"])
            streamtype = "youtube"
            img = details["thumb"]
            cap = _["play_10"].format(details["title"], details["duration_min"])
        elif await SoundCloud.valid(url):
            try:
                details, track_path = await SoundCloud.download(url)
            except Exception:
                return await _safe_edit_err(mystic, message, _["play_3"])
            duration_sec = details["duration_sec"]
            if duration_sec > config.DURATION_LIMIT:
                return await _safe_edit_err(
                    mystic,
                    message,
                    _["play_6"].format(
                        config.DURATION_LIMIT_MIN,
                        app.mention,
                    ),
                )
            try:
                await stream(
                    _,
                    mystic,
                    user_id,
                    details,
                    chat_id,
                    user_name,
                    message.chat.id,
                    streamtype="soundcloud",
                    forceplay=fplay,
                )
            except Exception as e:
                ex_type = type(e).__name__
                err = e if ex_type == "AssistantErr" else f"{ex_type}: {e}"
                return await _safe_edit_err(mystic, message, err)
            return
        else:
            try:
                await Hotty.stream_call(url)
            except NoActiveGroupCall:
                await _safe_edit_err(mystic, message, _["black_9"])
                return await app.send_message(
                    chat_id=config.LOGGER_ID,
                    text=_["play_17"],
                )
            except Exception as e:
                return await _safe_edit_err(mystic, message, f"{type(e).__name__}: {e}")
            await _safe_edit_err(mystic, message, _["str_2"])
            try:
                await stream(
                    _,
                    mystic,
                    message.from_user.id,
                    url,
                    chat_id,
                    message.from_user.first_name,
                    message.chat.id,
                    video=video,
                    streamtype="index",
                    forceplay=fplay,
                )
            except Exception as e:
                ex_type = type(e).__name__
                err = e if ex_type == "AssistantErr" else f"{ex_type}: {e}"
                return await _safe_edit_err(mystic, message, err)
            return await play_logs(message, streamtype="M3u8 or Index Link")
    else:
        if len(message.command) < 2:
            buttons = botplaylist_markup(_)
            try:
                await mystic.delete()
            except Exception:
                pass
            return await send_rich_block(message.chat.id, _["play_18"], buttons)
        slider = True
        query = message.text.split(None, 1)[1]
        if "-v" in query:
            query = query.replace("-v", "")
        try:
            details, track_id = await YouTube.track(query)
        except Exception:
            return await _safe_edit_err(mystic, message, _["play_3"])
        streamtype = "youtube"

    if str(playmode) == "Direct":
        if not plist_type:
            if details["duration_min"]:
                duration_sec = time_to_seconds(details["duration_min"])
                if duration_sec > config.DURATION_LIMIT:
                    return await _safe_edit_err(
                        mystic, message, _["play_6"].format(config.DURATION_LIMIT_MIN, app.mention)
                    )
            else:
                buttons = livestream_markup(
                    _,
                    track_id,
                    user_id,
                    "v" if video else "a",
                    "c" if channel else "g",
                    "f" if fplay else "d",
                )
                try:
                    await mystic.delete()
                except Exception:
                    pass
                return await send_rich_block(message.chat.id, _["play_13"], buttons)
        try:
            await stream(
                _,
                mystic,
                user_id,
                details,
                chat_id,
                user_name,
                message.chat.id,
                video=video,
                streamtype=streamtype,
                spotify=spotify,
                forceplay=fplay,
            )
        except Exception as e:
            ex_type = type(e).__name__
            err = e if ex_type == "AssistantErr" else f"{ex_type}: {e}"
            return await _safe_edit_err(mystic, message, err)
        return await play_logs(message, streamtype=streamtype)
    else:
        if plist_type:
            ran_hash = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=10)
            )
            lyrical[ran_hash] = plist_id
            buttons = playlist_markup(
                _,
                ran_hash,
                message.from_user.id,
                plist_type,
                "c" if channel else "g",
                "f" if fplay else "d",
            )
            try:
                await mystic.delete()
            except Exception:
                pass
            await send_rich_block(message.chat.id, cap, buttons, img_url=img)
            return await play_logs(message, streamtype=f"Playlist : {plist_type}")
        else:
            if slider:
                buttons = slider_markup(
                    _,
                    track_id,
                    message.from_user.id,
                    query,
                    0,
                    "c" if channel else "g",
                    "f" if fplay else "d",
                )
                try:
                    await mystic.delete()
                except Exception:
                    pass
                caption = _["play_10"].format(details["title"].title(), details["duration_min"])
                await send_rich_block(message.chat.id, caption, buttons, img_url=details["thumb"])
                return await play_logs(message, streamtype="Searched on Youtube")
            else:
                buttons = track_markup(
                    _,
                    track_id,
                    message.from_user.id,
                    "c" if channel else "g",
                    "f" if fplay else "d",
                )
                try:
                    await mystic.delete()
                except Exception:
                    pass
                await send_rich_block(message.chat.id, cap, buttons, img_url=img)
                return await play_logs(message, streamtype="URL Searched Inline")


# Callback Handler for "See Playlist" inside /play menu
@app.on_callback_query(filters.regex("see_plist_self") & ~BANNED_USERS)
async def see_plist_self_cb(client, CallbackQuery):
    user_id = CallbackQuery.from_user.id
    blocks_list, total_tracks, total_pages = await get_rich_see_page(user_id, page=0)
    if total_tracks == 0:
        return await CallbackQuery.answer("❌ Your playlist is empty!", show_alert=True)

    caption = (
        "<blockquote><emoji id=5895705279416241926>🎵</emoji> <u><b>SAVED PLAYLIST TRACKS</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        f"<emoji id=6066395745139824604>📊</emoji> Total tracks: <b>{total_tracks}</b>\n"
        "Tap any track to play and continue from that track onwards.</blockquote>"
    )
    blocks = html_to_rich_blocks(caption)
    blocks += blocks_list
    await edit_rich(CallbackQuery.message, blocks)


# Callback Handler for "Shuffle" inside /play menu
@app.on_callback_query(filters.regex(r"^stream_plist_self\|shuffle") & ~BANNED_USERS)
async def stream_plist_self_shuffle_cb(client, CallbackQuery):
    user_id = CallbackQuery.from_user.id
    notes = await _get_playlists(user_id)
    if not notes:
        return await CallbackQuery.answer("❌ Playlist is empty!", show_alert=True)

    chat_id = CallbackQuery.message.chat.id
    user_name = CallbackQuery.from_user.first_name or "User"

    try:
        await CallbackQuery.answer("🔀 Shuffling and starting stream...", show_alert=False)
        await CallbackQuery.message.delete()
    except Exception:
        pass

    await _call_db_func(remove_active_video_chat, chat_id)
    mystic = await client.send_message(chat_id, "🔄 **Fetching playlist & shuffling tracks...**")

    result = [str(k).strip() for k in notes.keys()]
    random.shuffle(result)

    try:
        from Oneforall.utils.database import get_lang
        from strings import get_string
        _ = get_string(await get_lang(chat_id))
        await stream(
            _,
            mystic,
            user_id,
            result,
            chat_id,
            user_name,
            chat_id,
            video=None,
            streamtype="playlist",
        )
    except Exception as e:
        return await mystic.edit_text(f"❌ Error starting stream: {e}")


# Handle "Load More" infinite suggestion pagination (Fresh random tracks on each page)
@app.on_callback_query(filters.regex(r"^suggest_more\|") & ~BANNED_USERS)
async def suggest_more_pagination(client, CallbackQuery):
    parts = CallbackQuery.data.split("|")
    page = int(parts[1])
    chat_id = CallbackQuery.message.chat.id

    cached = suggestion_cache.get(chat_id, [])

    # Fetch 20 new tracks from fresh random genres each time
    fresh = await fetch_random_diverse_tracks()
    if fresh:
        seen_ids = {t.get("id") for t in cached}
        seen_titles = {_clean_track_title(t.get("title", ""))[:14].lower() for t in cached}

        for item in fresh:
            item_id = item.get("id")
            item_title = _clean_track_title(item.get("title", ""))[:14].lower()
            if item_id not in seen_ids and item_title not in seen_titles:
                seen_ids.add(item_id)
                seen_titles.add(item_title)
                cached.append(item)

        suggestion_cache[chat_id] = cached

    if not cached:
        return await CallbackQuery.answer("❌ No more suggestions found!", show_alert=True)

    try:
        await CallbackQuery.answer("🔄 Loading fresh songs...", show_alert=False)
    except Exception:
        pass

    blocks = build_suggestion_blocks(cached, page=page)
    await edit_rich(CallbackQuery.message, blocks)


# Direct Play from Suggestion Button (Auto joins VC even if assistant is not in VC)
@app.on_callback_query(filters.regex(r"^suggest_play\|") & ~BANNED_USERS)
async def suggest_play_callback(client, CallbackQuery):
    vidid = CallbackQuery.data.split("|")[1]
    chat_id = CallbackQuery.message.chat.id
    user_id = CallbackQuery.from_user.id
    user_name = CallbackQuery.from_user.first_name

    try:
        await CallbackQuery.answer("▶️ Playing suggestion...", show_alert=False)
        await CallbackQuery.message.delete()
    except Exception:
        pass

    mystic = await client.send_message(chat_id, "🔄 **Fetching track & starting stream...**")

    try:
        details, track_id = await YouTube.track(vidid, True)
    except Exception as e:
        return await mystic.edit_text(f"❌ Error: {e}")

    try:
        from Oneforall.utils.database import get_lang
        from strings import get_string
        _ = get_string(await get_lang(chat_id))

        await stream(
            _,
            mystic,
            user_id,
            details,
            chat_id,
            user_name,
            chat_id,
            video=None,
            streamtype="youtube",
            forceplay=None,
        )
    except Exception as e:
        return await mystic.edit_text(f"❌ Playback error: {e}")


@app.on_callback_query(filters.regex("MusicStream") & ~BANNED_USERS)
@languageCB
async def play_music(client, CallbackQuery, _):
    callback_data = CallbackQuery.data.strip()
    callback_request = callback_data.split(None, 1)[1]
    vidid, user_id, mode, cplay, fplay = callback_request.split("|")
    if CallbackQuery.from_user.id != int(user_id):
        try:
            return await CallbackQuery.answer(_["playcb_1"], show_alert=True)
        except Exception:
            return
    try:
        chat_id, channel = await get_channeplayCB(_, cplay, CallbackQuery)
    except Exception:
        return
    user_name = CallbackQuery.from_user.first_name
    try:
        await CallbackQuery.message.delete()
        await CallbackQuery.answer()
    except Exception:
        pass
    mystic = await CallbackQuery.message.reply_text(
        _["play_2"].format(channel) if channel else _["play_1"]
    )
    try:
        details, track_id = await YouTube.track(vidid, True)
    except Exception as e:
        return await _safe_edit_err(mystic, CallbackQuery.message, _["play_3"])
    if details["duration_min"]:
        duration_sec = time_to_seconds(details["duration_min"])
        if duration_sec > config.DURATION_LIMIT:
            return await _safe_edit_err(
                mystic, CallbackQuery.message, _["play_6"].format(config.DURATION_LIMIT_MIN, app.mention)
            )
    else:
        buttons = livestream_markup(
            _,
            track_id,
            CallbackQuery.from_user.id,
            mode,
            "c" if cplay == "c" else "g",
            "f" if fplay else "d",
        )
        try:
            await mystic.delete()
        except Exception:
            pass
        return await send_rich_block(CallbackQuery.message.chat.id, _["play_13"], buttons)
    video = True if mode == "v" else None
    ffplay = True if fplay == "f" else None
    try:
        await stream(
            _,
            mystic,
            CallbackQuery.from_user.id,
            details,
            chat_id,
            user_name,
            CallbackQuery.message.chat.id,
            video,
            streamtype="youtube",
            forceplay=ffplay,
        )
    except Exception as e:
        ex_type = type(e).__name__
        err = e if ex_type == "AssistantErr" else f"{ex_type}: {e}"
        return await _safe_edit_err(mystic, CallbackQuery.message, err)
    return


@app.on_callback_query(filters.regex("AnonymousAdmin") & ~BANNED_USERS)
async def piyush_check(client, CallbackQuery):
    try:
        await CallbackQuery.answer(
            "» ʀᴇᴠᴇʀᴛ ʙᴀᴄᴋ ᴛᴏ ᴜsᴇʀ ᴀᴄᴄᴏᴜɴᴛ :\n\n"
            "ᴏᴘᴇɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ sᴇᴛᴛɪɴɢs.\n"
            "-> ᴀᴅᴍɪɴɪsᴛʀᴀᴛᴏʀs\n"
            "-> ᴄʟɪᴄᴋ ᴏɴ ʏᴏᴜʀ ɴᴀᴍᴇ\n"
            "-> ᴜɴᴄʜᴇᴄᴋ ᴀɴᴏɴʏᴍᴏᴜs ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴs.",
            show_alert=True,
        )
    except Exception:
        pass


@app.on_callback_query(filters.regex("HottyPlaylists") & ~BANNED_USERS)
@languageCB
async def play_playlists_command(client, CallbackQuery, _):
    callback_data = CallbackQuery.data.strip()
    callback_request = callback_data.split(None, 1)[1]
    (
        videoid,
        user_id,
        ptype,
        mode,
        cplay,
        fplay,
    ) = callback_request.split("|")
    if CallbackQuery.from_user.id != int(user_id):
        try:
            return await CallbackQuery.answer(_["playcb_1"], show_alert=True)
        except Exception:
            return
    try:
        chat_id, channel = await get_channeplayCB(_, cplay, CallbackQuery)
    except Exception:
        return
    user_name = CallbackQuery.from_user.first_name
    try:
        await CallbackQuery.message.delete()
        await CallbackQuery.answer()
    except Exception:
        pass
    mystic = await CallbackQuery.message.reply_text(
        _["play_2"].format(channel) if channel else _["play_1"]
    )
    videoid = lyrical.get(videoid)
    video = True if mode == "v" else None
    ffplay = True if fplay == "f" else None
    spotify = True
    if ptype == "yt":
        spotify = False
        try:
            result = await YouTube.playlist(
                videoid,
                config.PLAYLIST_FETCH_LIMIT,
                CallbackQuery.from_user.id,
                True,
            )
        except Exception:
            return await _safe_edit_err(mystic, CallbackQuery.message, _["play_3"])
    if ptype == "spplay":
        try:
            result, spotify_id = await Spotify.playlist(videoid)
        except Exception:
            return await _safe_edit_err(mystic, CallbackQuery.message, _["play_3"])
    if ptype == "spalbum":
        try:
            result, spotify_id = await Spotify.album(videoid)
        except Exception:
            return await _safe_edit_err(mystic, CallbackQuery.message, _["play_3"])
    if ptype == "spartist":
        try:
            result, spotify_id = await Spotify.artist(videoid)
        except Exception:
            return await _safe_edit_err(mystic, CallbackQuery.message, _["play_3"])
    if ptype == "apple":
        try:
            result, apple_id = await Apple.playlist(videoid, True)
        except Exception:
            return await _safe_edit_err(mystic, CallbackQuery.message, _["play_3"])
    try:
        await stream(
            _,
            mystic,
            user_id,
            result,
            chat_id,
            user_name,
            CallbackQuery.message.chat.id,
            video,
            streamtype="playlist",
            spotify=spotify,
            forceplay=ffplay,
        )
    except Exception as e:
        ex_type = type(e).__name__
        err = e if ex_type == "AssistantErr" else f"{ex_type}: {e}"
        return await _safe_edit_err(mystic, CallbackQuery.message, err)
    return


@app.on_callback_query(filters.regex("slider") & ~BANNED_USERS)
@languageCB
async def slider_queries(client, CallbackQuery, _):
    callback_data = CallbackQuery.data.strip()
    callback_request = callback_data.split(None, 1)[1]
    (
        what,
        rtype,
        query,
        user_id,
        cplay,
        fplay,
    ) = callback_request.split("|")
    if CallbackQuery.from_user.id != int(user_id):
        try:
            return await CallbackQuery.answer(_["playcb_1"], show_alert=True)
        except Exception:
            return
    what = str(what)
    rtype = int(rtype)
    if what == "F":
        query_type = 0 if rtype == 9 else int(rtype + 1)
        try:
            await CallbackQuery.answer(_["playcb_2"])
        except Exception:
            pass
        title, duration_min, thumbnail, vidid = await YouTube.slider(query, query_type)
        buttons = slider_markup(_, vidid, user_id, query, query_type, cplay, fplay)
        caption = _["play_10"].format(title.title(), duration_min)
        try:
            await CallbackQuery.message.delete()
        except Exception:
            pass
        return await send_rich_block(CallbackQuery.message.chat.id, caption, buttons, img_url=thumbnail)
    if what == "B":
        query_type = 9 if rtype == 0 else int(rtype - 1)
        try:
            await CallbackQuery.answer(_["playcb_2"])
        except Exception:
            pass
        title, duration_min, thumbnail, vidid = await YouTube.slider(query, query_type)
        buttons = slider_markup(_, vidid, user_id, query, query_type, cplay, fplay)
        caption = _["play_10"].format(title.title(), duration_min)
        try:
            await CallbackQuery.message.delete()
        except Exception:
            pass
        return await send_rich_block(CallbackQuery.message.chat.id, caption, buttons, img_url=thumbnail)
