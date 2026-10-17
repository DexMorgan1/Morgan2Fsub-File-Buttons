import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated

from bot import Bot
from config import (ADMINS, FORCE_MSG, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON,
                    PROTECT_CONTENT)
from helper_func import file_update_keyboard, subscribed, decode, get_messages
from database.database import (
    add_user, del_user, full_userbase, present_user,
    get_force_subscriptions, get_or_create_force_subscribe_link,
    save_pending_file_request, toggle_force_subscription,
)


@Bot.on_message(filters.command('start') & filters.private & subscribed)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    if not await present_user(user_id):
        try:
            await add_user(user_id)
        except Exception:
            pass

    if len(message.text) <= 7:
        reply_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("⚡️ ᴀʙᴏᴜᴛ", callback_data="about"),
            InlineKeyboardButton("🍁 ᴘʀᴇᴍɪᴜᴍ", url="https://t.me/SeriesAchievers"),
        ]])
        await message.reply_text(
            START_MSG.format(
                first=message.from_user.first_name,
                last=message.from_user.last_name,
                username=None if not message.from_user.username else '@' + message.from_user.username,
                mention=message.from_user.mention,
                id=user_id,
            ),
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
        return

    try:
        argument = (await decode(message.text.split(" ", 1)[1])).split("-")
        if len(argument) == 3:
            start = int(int(argument[1]) / abs(client.db_channel.id))
            end = int(int(argument[2]) / abs(client.db_channel.id))
            ids = range(start, end + 1) if start <= end else range(start, end - 1, -1)
        elif len(argument) == 2:
            ids = [int(int(argument[1]) / abs(client.db_channel.id))]
        else:
            return
    except Exception:
        return

    waiting = await message.reply("Wait A Second...")
    try:
        messages = await get_messages(client, ids)
    except Exception:
        await waiting.edit("Something went wrong..!")
        return
    await waiting.delete()

    for msg in messages:
        caption = "" if not msg.caption else msg.caption.html
        if CUSTOM_CAPTION and msg.document:
            caption = CUSTOM_CAPTION.format(previouscaption=caption, filename=msg.document.file_name)
        source_markup = msg.reply_markup if DISABLE_CHANNEL_BUTTON else None
        reply_markup = file_update_keyboard(source_markup)
        try:
            await msg.copy(
                chat_id=user_id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                protect_content=PROTECT_CONTENT,
            )
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
        except Exception:
            pass


@Bot.on_message(filters.command('start') & filters.private)
async def not_joined(client: Client, message: Message):
    try:
        await save_pending_file_request(message.from_user.id, message.command[1])
    except (IndexError, AttributeError):
        pass

    buttons = []
    join_buttons = []
    for channel in await get_force_subscriptions():
        if not channel['enabled'] or not channel['channel_id']:
            continue
        try:
            async def create_request_link():
                return await client.create_chat_invite_link(
                    chat_id=channel['channel_id'],
                    name=f"force-subscribe-{channel['slot']}",
                    creates_join_request=True,
                )

            invite_link = await get_or_create_force_subscribe_link(
                channel['slot'], create_request_link,
            )
            join_buttons.append(InlineKeyboardButton(
                text=f"🔵 Join Channel {channel['slot']} 📢",
                url=invite_link,
            ))
        except Exception as error:
            client.LOGGER(__name__).warning("Unable to create request link: %s", error)

    if join_buttons:
        buttons.extend([[button] for button in join_buttons])

    try:
        buttons.append([InlineKeyboardButton(
            text="🟢 Try Again 🔄",
            url=f"https://t.me/{client.username}?start={message.command[1]}",
        )])
    except IndexError:
        pass

    await message.reply(
        text=FORCE_MSG.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name,
            username=None if not message.from_user.username else '@' + message.from_user.username,
            mention=message.from_user.mention,
            id=message.from_user.id,
        ),
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True,
    )


def force_subscribe_keyboard(channels):
    rows = []
    for channel in channels:
        if channel['channel_id']:
            state = "ON" if channel['enabled'] else "OFF"
            rows.append([InlineKeyboardButton(
                text=f"Channel {channel['slot']}: {state}",
                callback_data=f"fsub:toggle:{channel['slot']}",
            )])
    return InlineKeyboardMarkup(rows) if rows else None


@Bot.on_message(filters.command('fsub') & filters.private & filters.user(ADMINS))
async def force_subscribe_settings(client: Client, message: Message):
    channels = await get_force_subscriptions()
    await message.reply_text(
                """<b>Force Subscribe Settings</b>

Tap a channel to turn its force-subscription check ON or OFF.""",
        reply_markup=force_subscribe_keyboard(channels),
    )


@Bot.on_callback_query(filters.regex(r"^fsub:toggle:(1|2)$") & filters.user(ADMINS))
async def toggle_force_subscribe_setting(client: Client, query: CallbackQuery):
    slot = int(query.data.rsplit(":", 1)[1])
    enabled = await toggle_force_subscription(slot)
    await query.answer(f"Channel {slot} is now {'ON' if enabled else 'OFF'}")
    await query.edit_message_reply_markup(force_subscribe_keyboard(await get_force_subscriptions()))


@Bot.on_message(filters.command('users') & filters.private & filters.user(ADMINS))
async def get_users(client: Bot, message: Message):
    await message.reply_text(f"{len(await full_userbase())} users are using this bot")


@Bot.on_message(filters.private & filters.command('broadcast') & filters.user(ADMINS))
async def broadcast(client: Bot, message: Message):
    if not message.reply_to_message:
        return await message.reply("Reply to a message with /broadcast.")
    sent = 0
    for chat_id in await full_userbase():
        try:
            source_message = message.reply_to_message
            copy_options = {}
            if source_message.media:
                source_markup = source_message.reply_markup if DISABLE_CHANNEL_BUTTON else None
                copy_options["reply_markup"] = file_update_keyboard(source_markup)
            await source_message.copy(chat_id, **copy_options)
            sent += 1
        except (UserIsBlocked, InputUserDeactivated):
            await del_user(chat_id)
        except FloodWait as error:
            await asyncio.sleep(error.x)
        except Exception:
            pass
    await message.reply(f"Broadcast completed: {sent} delivered.")
