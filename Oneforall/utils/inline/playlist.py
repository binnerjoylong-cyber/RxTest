from pyrogram import enums, types


def botplaylist_markup(_):
    return [
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text="👁️ See Playlist",
                    style=enums.ButtonStyle.SUCCESS,
                    callback_data="see_plist_self",
                ),
                types.RichMessageButton(
                    text="🔀 Shuffle",
                    style=enums.ButtonStyle.PRIMARY,
                    callback_data="stream_plist_self|shuffle",
                ),
            ]
        ),
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=_["PL_B_1"],
                    style=enums.ButtonStyle.DEFAULT,
                    callback_data="get_playlist_playmode",
                ),
            ]
        ),
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=_["CLOSE_BUTTON"],
                    style=enums.ButtonStyle.DANGER,
                    callback_data="close",
                ),
            ]
        ),
    ]


def get_playlist_markup(_):
    return [
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text="👁️ See Playlist",
                    style=enums.ButtonStyle.SUCCESS,
                    callback_data="see_plist_self",
                ),
                types.RichMessageButton(
                    text="🔀 Shuffle",
                    style=enums.ButtonStyle.PRIMARY,
                    callback_data="stream_plist_self|shuffle",
                ),
            ]
        ),
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=_["P_B_1"],
                    style=enums.ButtonStyle.DEFAULT,
                    callback_data="play_playlist a",
                ),
                types.RichMessageButton(
                    text=_["P_B_2"],
                    style=enums.ButtonStyle.DEFAULT,
                    callback_data="play_playlist v",
                ),
            ]
        ),
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=_["BACK_BUTTON"],
                    style=enums.ButtonStyle.DEFAULT,
                    callback_data="home_play",
                ),
                types.RichMessageButton(
                    text=_["CLOSE_BUTTON"],
                    style=enums.ButtonStyle.DANGER,
                    callback_data="close",
                ),
            ]
        ),
    ]


def top_play_markup(_):
    return [
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=_["PL_B_9"],
                    style=enums.ButtonStyle.SUCCESS,
                    callback_data="SERVERTOP Global",
                ),
            ]
        ),
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=_["PL_B_10"],
                    style=enums.ButtonStyle.PRIMARY,
                    callback_data="SERVERTOP Group",
                ),
            ]
        ),
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=_["PL_B_11"],
                    style=enums.ButtonStyle.PRIMARY,
                    callback_data="SERVERTOP Personal",
                ),
            ]
        ),
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=_["BACK_BUTTON"],
                    style=enums.ButtonStyle.DEFAULT,
                    callback_data="get_playmarkup",
                ),
                types.RichMessageButton(
                    text=_["CLOSE_BUTTON"],
                    style=enums.ButtonStyle.DANGER,
                    callback_data="close",
                ),
            ]
        ),
    ]


def failed_top_markup(_):
    return [
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=_["BACK_BUTTON"],
                    style=enums.ButtonStyle.DEFAULT,
                    callback_data="get_top_playlists",
                ),
                types.RichMessageButton(
                    text=_["CLOSE_BUTTON"],
                    style=enums.ButtonStyle.DANGER,
                    callback_data="close",
                ),
            ]
        ),
    ]


def warning_markup(_):
    return [
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=_["PL_B_7"],
                    style=enums.ButtonStyle.DANGER,
                    callback_data="delete_whole_playlist",
                ),
            ]
        ),
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=_["BACK_BUTTON"],
                    style=enums.ButtonStyle.DEFAULT,
                    callback_data="del_back_playlist",
                ),
                types.RichMessageButton(
                    text=_["CLOSE_BUTTON"],
                    style=enums.ButtonStyle.DANGER,
                    callback_data="close",
                ),
            ]
        ),
    ]


def close_markup(_):
    return [
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text=_["CLOSE_BUTTON"],
                    style=enums.ButtonStyle.DANGER,
                    callback_data="close",
                ),
            ]
        )
    ]
