#(©)CodeFlix_Bots

import asyncio
import base64
import re

import aiohttp
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import Bot
from config import (
    AUTO_APPROVE_JOIN_REQUESTS,
    CUSTOM_CAPTION,
    DISABLE_CHANNEL_BUTTON,
    FILE_UPDATE_BUTTONS_ENABLED,
    MOVIES_BUTTON_LINK,
    MOVIES_BUTTON_TEXT,
    PROTECT_CONTENT,
    TG_BOT_TOKEN,
    TV_SHOW_BUTTON_LINK,
    TV_SHOW_BUTTON_TEXT,
)
from database.database import (
    clear_pending_file_request,
    get_force_subscriptions,
    get_pending_file_request,
    has_pending_join_request,
    remember_join_request,
)


async def is_subscribed(filter, client, update):
    """Check membership in every enabled force-subscribe channel."""
    user_id = update.from_user.id
    valid_statuses = {
        ChatMemberStatus.OWNER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.RESTRICTED,
    }
    for channel in await get_force_subscriptions():
        if not channel["enabled"] or not channel["channel_id"]:
            continue
        try:
            member = await client.get_chat_member(channel["channel_id"], user_id)
            if member.status in valid_statuses:
                continue
        except UserNotParticipant:
            pass
        except Exception as error:
            client.LOGGER(__name__).warning("Channel %s membership check failed: %s", channel['slot'], error)
        return False
    return True

async def encode(string):
    string_bytes = string.encode("ascii")
    base64_bytes = base64.urlsafe_b64encode(string_bytes)
    return (base64_bytes.decode("ascii")).strip("=")


async def decode(base64_string):
    base64_string = base64_string.strip("=")
    base64_bytes = (base64_string + "=" * (-len(base64_string) % 4)).encode("ascii")
    return base64.urlsafe_b64decode(base64_bytes).decode("ascii")


async def get_messages(client, message_ids):
    messages = []
    total_messages = 0
    while total_messages != len(message_ids):
        temb_ids = message_ids[total_messages:total_messages + 200]
        try:
            msgs = await client.get_messages(chat_id=client.db_channel.id, message_ids=temb_ids)
        except FloodWait as error:
            await asyncio.sleep(error.x)
            msgs = await client.get_messages(chat_id=client.db_channel.id, message_ids=temb_ids)
        except Exception:
            msgs = []
        total_messages += len(temb_ids)
        messages.extend(msgs)
    return messages


async def get_message_id(client, message):
    if message.forward_from_chat:
        return message.forward_from_message_id if message.forward_from_chat.id == client.db_channel.id else 0
    if message.forward_sender_name:
        return 0
    if message.text:
        pattern = "https://t.me/(?:c/)?(.*)/(\d+)"
        matches = re.match(pattern, message.text)
        if not matches:
            return 0
        channel_id = matches.group(1)
        msg_id = int(matches.group(2))
        if channel_id.isdigit() and f"-100{channel_id}" == str(client.db_channel.id):
            return msg_id
        if not channel_id.isdigit() and channel_id == client.db_channel.username:
            return msg_id
    return 0


def file_update_keyboard(existing_markup=None):
    """Add Railway-configured TV Show and Movies links beneath a file.

    Existing inline buttons are retained, so sharing and other source-channel
    buttons continue to work. Empty link variables safely hide only their
    corresponding update button.
    """
    if not FILE_UPDATE_BUTTONS_ENABLED:
        return existing_markup

    rows = [list(row) for row in existing_markup.inline_keyboard] if existing_markup else []

    update_buttons = []
    if TV_SHOW_BUTTON_LINK:
        update_buttons.append(InlineKeyboardButton(TV_SHOW_BUTTON_TEXT, url=TV_SHOW_BUTTON_LINK))
    if MOVIES_BUTTON_LINK:
        update_buttons.append(InlineKeyboardButton(MOVIES_BUTTON_TEXT, url=MOVIES_BUTTON_LINK))

    if update_buttons:
        rows.append(update_buttons)

    return InlineKeyboardMarkup(rows) if rows else None


def has_file_update_buttons():
    """Return whether there is an update button that should be shown."""
    return FILE_UPDATE_BUTTONS_ENABLED and bool(
        TV_SHOW_BUTTON_LINK or MOVIES_BUTTON_LINK
    )


def _button_payload(button):
    """Convert the existing Pyrogram button fields to Bot API JSON."""
    payload = {"text": button.text}
    for field in (
        "url", "callback_data", "switch_inline_query",
        "switch_inline_query_current_chat",
    ):
        value = getattr(button, field, None)
        if value is not None:
            payload[field] = value
    return payload


def file_update_button_payload(existing_markup=None):
    """Build a Bot API keyboard with Telegram's solid-blue button style.

    Pyrogram's current keyboard class cannot send the Bot API ``style`` field.
    We therefore use this JSON payload only with the Bot API copy/edit methods,
    while ``file_update_keyboard`` remains a safe Pyrogram fallback.
    """
    if not has_file_update_buttons():
        return None

    rows = []
    if existing_markup:
        rows = [
            [_button_payload(button) for button in row]
            for row in existing_markup.inline_keyboard
        ]

    update_buttons = []
    if TV_SHOW_BUTTON_LINK:
        update_buttons.append({
            "text": TV_SHOW_BUTTON_TEXT,
            "url": TV_SHOW_BUTTON_LINK,
            "style": "primary",
        })
    if MOVIES_BUTTON_LINK:
        update_buttons.append({
            "text": MOVIES_BUTTON_TEXT,
            "url": MOVIES_BUTTON_LINK,
            "style": "primary",
        })

    if update_buttons:
        # Both update buttons belong in one row: left and right.
        rows.append(update_buttons)

    return {"inline_keyboard": rows}


async def _bot_api_call(method, payload, logger):
    """Call Telegram's Bot API without ever logging its authentication URL."""
    if not TG_BOT_TOKEN:
        return None

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"https://api.telegram.org/bot{TG_BOT_TOKEN}/{method}",
                json=payload,
            ) as response:
                result = await response.json(content_type=None)
    except Exception as error:
        logger.warning("Telegram Bot API %s request failed: %s", method, error)
        return None

    if result.get("ok"):
        return result.get("result")

    logger.warning(
        "Telegram Bot API %s request was rejected: %s",
        method,
        result.get("description", "unknown error"),
    )
    return None


async def copy_file_with_styled_buttons(
    client: Bot,
    source_message,
    chat_id,
    caption,
    existing_markup=None,
):
    """Copy a media message with real blue file-update buttons when possible.

    Returning ``False`` lets the caller fall back to Pyrogram, so a temporary
    Bot API issue can never prevent a user from receiving their file.
    """
    reply_markup = file_update_button_payload(existing_markup)
    if not reply_markup or not getattr(source_message, "media", None):
        return False

    payload = {
        "chat_id": chat_id,
        "from_chat_id": source_message.chat.id,
        "message_id": source_message.id,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": reply_markup,
        "protect_content": PROTECT_CONTENT,
    }
    result = await _bot_api_call("copyMessage", payload, client.LOGGER(__name__))
    return result is not None


async def send_force_subscribe_message(client: Bot, message, text, buttons):
    """Send the join screen with blue Join buttons and a green retry button."""
    if not buttons:
        return False

    rows = []
    for row_index, row in enumerate(buttons):
        styled_row = []
        for button in row:
            payload = _button_payload(button)
            payload["style"] = "success" if row_index == len(buttons) - 1 else "primary"
            styled_row.append(payload)
        rows.append(styled_row)

    payload = {
        "chat_id": message.chat.id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": rows},
        "disable_web_page_preview": True,
    }
    return await _bot_api_call("sendMessage", payload, client.LOGGER(__name__)) is not None


def get_readable_time(seconds: int) -> str:
    count = 0
    up_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]
    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)
    for index in range(len(time_list)):
        time_list[index] = str(time_list[index]) + time_suffix_list[index]
    if len(time_list) == 4:
        up_time += f"{time_list.pop()}, "
    time_list.reverse()
    return up_time + ":".join(time_list)


async def deliver_pending_file(client: Bot, user_id: int):
    """Send the file saved when this user first opened its deep link."""
    payload = await get_pending_file_request(user_id)
    if not payload:
        return

    try:
        argument = (await decode(payload)).split("-")
        if len(argument) == 3:
            start = int(int(argument[1]) / abs(client.db_channel.id))
            end = int(int(argument[2]) / abs(client.db_channel.id))
            ids = range(start, end + 1) if start <= end else range(start, end - 1, -1)
        elif len(argument) == 2:
            ids = [int(int(argument[1]) / abs(client.db_channel.id))]
        else:
            return
        messages = await get_messages(client, ids)
    except Exception as error:
        client.LOGGER(__name__).warning("Unable to prepare pending file: %s", error)
        return

    sent = False
    for msg in messages:
        if not msg:
            continue
        caption = "" if not msg.caption else msg.caption.html
        if CUSTOM_CAPTION and msg.document:
            caption = CUSTOM_CAPTION.format(previouscaption=caption, filename=msg.document.file_name)
        source_markup = msg.reply_markup if DISABLE_CHANNEL_BUTTON else None
        reply_markup = file_update_keyboard(source_markup)
        try:
            if await copy_file_with_styled_buttons(
                client, msg, user_id, caption, source_markup,
            ):
                sent = True
                await asyncio.sleep(0.5)
                continue
            await msg.copy(
                chat_id=user_id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                protect_content=PROTECT_CONTENT,
            )
            sent = True
            await asyncio.sleep(0.5)
        except FloodWait as error:
            await asyncio.sleep(error.x)
            await msg.copy(
                chat_id=user_id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                protect_content=PROTECT_CONTENT,
            )
            sent = True
        except Exception as error:
            client.LOGGER(__name__).warning("Unable to deliver pending file: %s", error)

    if sent:
        await clear_pending_file_request(user_id)


subscribed = filters.create(is_subscribed)


@Bot.on_chat_join_request()
async def record_verified_join_request(client: Bot, join_request):
    """Record requests and deliver once every enabled channel is satisfied."""
    active_channels = {
        channel['channel_id']
        for channel in await get_force_subscriptions()
        if channel['enabled'] and channel['channel_id']
    }
    if join_request.chat.id not in active_channels:
        return

    user_id = join_request.from_user.id
    await remember_join_request(join_request.chat.id, user_id)
    if AUTO_APPROVE_JOIN_REQUESTS:
        try:
            await client.approve_chat_join_request(join_request.chat.id, user_id)
            await asyncio.sleep(1)
        except Exception as error:
            client.LOGGER(__name__).warning("Could not approve join request: %s", error)
            return
    if await is_subscribed(None, client, join_request):
        await deliver_pending_file(client, user_id)
