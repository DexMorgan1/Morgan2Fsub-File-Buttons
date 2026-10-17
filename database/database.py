#(©)CodeXBotz

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import pymongo
from pymongo import ReturnDocument
from config import (
    DB_URI,
    DB_NAME,
    FORCE_SUB_CHANNEL,
    FORCE_SUB_CHANNEL_ENABLED,
    FORCE_SUB_CHANNEL2,
    FORCE_SUB_CHANNEL2_ENABLED,
)


dbclient = pymongo.MongoClient(DB_URI)
database = dbclient[DB_NAME]


user_data = database['users']
force_sub_data = database['force_sub_settings']
pending_join_data = database['pending_join_requests']
pending_file_data = database['pending_file_requests']


async def present_user(user_id: int):
    return bool(user_data.find_one({'_id': user_id}))


async def add_user(user_id: int):
    user_data.insert_one({'_id': user_id})


async def full_userbase():
    return [doc['_id'] for doc in user_data.find()]


async def del_user(user_id: int):
    user_data.delete_one({'_id': user_id})


def _default_force_subscriptions():
    return [
        {'slot': 1, 'channel_id': FORCE_SUB_CHANNEL, 'enabled': FORCE_SUB_CHANNEL_ENABLED},
        {'slot': 2, 'channel_id': FORCE_SUB_CHANNEL2, 'enabled': FORCE_SUB_CHANNEL2_ENABLED},
    ]


async def get_force_subscriptions():
    """Return configured channels and reset a slot when its channel changes."""
    channels = []
    for default in _default_force_subscriptions():
        saved = force_sub_data.find_one({'_id': default['slot']})
        channel_changed = saved is not None and saved.get('channel_id') != default['channel_id']
        link_mode_changed = saved is not None and saved.get('invite_mode') != 'request_to_join'
        if saved is None or channel_changed or link_mode_changed:
            force_sub_data.update_one(
                {'_id': default['slot']},
                {'$set': {
                    'channel_id': default['channel_id'],
                    'enabled': default['enabled'],
                }, '$unset': {'invite_link': '', 'creation_token': '', 'creation_lock_until': ''}},
                upsert=True,
            )
            enabled = default['enabled']
        else:
            enabled = bool(saved.get('enabled', default['enabled']))
        channels.append({**default, 'enabled': enabled})
    return channels


async def remember_join_request(channel_id: int, user_id: int):
    """Allow a verified join request to access files for the next 24 hours."""
    pending_join_data.update_one(
        {'_id': f'{channel_id}:{user_id}'},
        {'$set': {
            'channel_id': channel_id,
            'user_id': user_id,
            'expires_at': datetime.utcnow() + timedelta(hours=24),
        }},
        upsert=True,
    )


async def has_pending_join_request(channel_id: int, user_id: int):
    record = pending_join_data.find_one({'_id': f'{channel_id}:{user_id}'})
    if not record:
        return False
    if record.get('expires_at') and record['expires_at'] < datetime.utcnow():
        pending_join_data.delete_one({'_id': record['_id']})
        return False
    return True


async def save_pending_file_request(user_id: int, payload: str):
    """Remember the most recent file link a user tried to open."""
    pending_file_data.update_one(
        {'_id': user_id},
        {'$set': {'payload': payload, 'created_at': datetime.utcnow()}},
        upsert=True,
    )


async def get_pending_file_request(user_id: int):
    record = pending_file_data.find_one({'_id': user_id})
    return record.get('payload') if record else None


async def clear_pending_file_request(user_id: int):
    pending_file_data.delete_one({'_id': user_id})


async def get_or_create_force_subscribe_link(slot: int, create_link):
    """Reuse exactly one request-to-join link per channel slot.

    A MongoDB lease prevents two simultaneous visitors from creating multiple
    invite links before the first URL is saved.
    """
    while True:
        saved = force_sub_data.find_one({'_id': slot}) or {}
        invite_link = saved.get('invite_link')
        if invite_link and saved.get('invite_mode') == 'request_to_join':
            return invite_link

        now = datetime.utcnow()
        token = uuid4().hex
        claimed = force_sub_data.find_one_and_update(
            {
                '_id': slot,
                '$and': [
                    {'$or': [
                        {'invite_link': {'$exists': False}},
                        {'invite_link': None},
                    ]},
                    {'$or': [
                        {'creation_lock_until': {'$exists': False}},
                        {'creation_lock_until': {'$lt': now}},
                    ]},
                ],
            },
            {'$set': {
                'creation_token': token,
                'creation_lock_until': now + timedelta(minutes=2),
            }},
            return_document=ReturnDocument.AFTER,
        )
        if not claimed:
            await asyncio.sleep(0.25)
            continue

        try:
            invite = await create_link()
        except Exception:
            force_sub_data.update_one(
                {'_id': slot, 'creation_token': token},
                {'$unset': {'creation_token': '', 'creation_lock_until': ''}},
            )
            raise

        saved = force_sub_data.update_one(
            {'_id': slot, 'creation_token': token},
            {
                '$set': {
                    'invite_link': invite.invite_link,
                    'invite_mode': 'request_to_join',
                    'created_at': datetime.utcnow(),
                },
                '$unset': {'creation_token': '', 'creation_lock_until': ''},
            },
        )
        if saved.modified_count:
            return invite.invite_link


async def toggle_force_subscription(slot: int):
    """Flip one Force Subscribe slot and return its new state."""
    channels = await get_force_subscriptions()
    setting = next((item for item in channels if item['slot'] == slot), None)
    if setting is None:
        raise ValueError('Unknown Force Subscribe slot')

    new_state = not setting['enabled']
    force_sub_data.update_one(
        {'_id': slot},
        {'$set': {'enabled': new_state}},
        upsert=True,
    )
    return new_state
