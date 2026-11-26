"""大廳房間：建立、加入、離開、開始、觀戰前檢查，以及清掉沒人的房間。

建房、入房都要帶登入 token，房內玩家的 ID 以 token 為準（不能冒用別人的身分入座）。
"""
import random

import gevent
from flask import request
from flask_socketio import join_room, leave_room, emit

from server.extensions import socketio
from server.state import rooms, sid_info, lobby_sids
from server.engine.game import init_game_state, room_timer_loop
from server.auth_token import verify
from server import validation as v

MAX_PLAYERS = 4
ROOM_IDLE_SECONDS = 60   # 對局中所有人都離線超過這麼久，就把房間清掉


def spectator_names(room_code):
    return [i['name'] for i in sid_info.values() if i['room'] == room_code and i['spectator']]


def new_room_code(wanted=None):
    """用前端產生的房號；已經被用掉（或格式不對）就換一個還沒人用的。全部 9000 個都滿了回傳 None。"""
    code = v.room_code(wanted)
    if code and code not in rooms:
        return code
    free = [str(n) for n in range(1000, 10000) if str(n) not in rooms]
    return random.choice(free) if free else None


def _player_info(uid, user_info):
    user_info = user_info if isinstance(user_info, dict) else {}
    name = v.clean_name(user_info.get('name'), uid)
    return {'id': uid, 'name': name, 'avatar': v.clean_name(user_info.get('avatar'), name[0].upper(), v.AVATAR_MAX)}


def _room_payload(room_code):
    room = rooms[room_code]
    return {'room_code': room_code, 'players': room['players'], 'rules': room.get('rules', 1)}


def delete_room(room_code):
    room = rooms.pop(room_code, None)
    job = room and room.get('game_state', {}).get('timer_job')
    if job:
        job.kill()


def remove_waiting_player(room_code, uid):
    """把玩家移出等待中的房間；空了就刪掉房間，否則通知其他人。"""
    room = rooms.get(room_code)
    if not room:
        return
    room['players'] = [p for p in room['players'] if p['id'] != uid]
    if not room['players']:
        delete_room(room_code)
    else:
        emit('room_updated', _room_payload(room_code), to=room_code)


def cleanup_if_idle(room_code):
    """對局中的房間：沒有任何對局頁連線（玩家、觀戰者）就刪掉，停掉計時器。"""
    room = rooms.get(room_code)
    if room and room.get('status') == 'playing' \
            and not any(i['room'] == room_code for i in sid_info.values()) \
            and not any(rc == room_code for rc, _ in lobby_sids.values()):
        delete_room(room_code)
        return True
    return False


def schedule_idle_cleanup(room_code, delay=None):
    gevent.spawn_later(ROOM_IDLE_SECONDS if delay is None else delay, cleanup_if_idle, room_code)


def _leave_previous_room(sid, uid):
    """同一個連線本來在別的等待室（例如先建房、又去加入別人的房），先把他移出原本的房間。"""
    old = lobby_sids.pop(sid, None)
    if old and old[0] in rooms:
        leave_room(old[0])
        if rooms[old[0]].get('status') == 'waiting':
            remove_waiting_player(old[0], uid)


def lobby_disconnect(sid):
    """大廳連線斷掉：等待中的房間把他移出去；已經開局的房間不動（玩家正在換到對局頁）。"""
    entry = lobby_sids.pop(sid, None)
    if not entry:
        return
    room_code, uid = entry
    room = rooms.get(room_code)
    if not room:
        return
    if room.get('status') == 'waiting':
        # 同一個人可能開了兩個分頁，另一個分頁還在就不移除
        if not any(e == (room_code, uid) for e in lobby_sids.values()):
            remove_waiting_player(room_code, uid)
    else:
        schedule_idle_cleanup(room_code)


@socketio.on('create_room')
def handle_create_room(data):
    data = data if isinstance(data, dict) else {}
    uid = verify(data.get('token'))
    if not uid:
        return emit('join_error', {'message': '請先登入再建立房間。'})
    room_code = new_room_code(data.get('room_code'))
    if not room_code:
        return emit('join_error', {'message': '伺服器房間已滿，請稍後再試。'})

    _leave_previous_room(request.sid, uid)
    join_room(room_code)
    rules = 2 if data.get('rules') == 2 else 1
    rooms[room_code] = {'players': [_player_info(uid, data.get('user_info'))], 'status': 'waiting', 'rules': rules}
    lobby_sids[request.sid] = (room_code, uid)
    emit('room_created', _room_payload(room_code))


@socketio.on('join_room')
def handle_join_room(data):
    data = data if isinstance(data, dict) else {}
    uid = verify(data.get('token'))
    if not uid:
        return emit('join_error', {'message': '請先登入再加入房間。'})
    room_code = v.room_code(data.get('room_code'))
    room = rooms.get(room_code) if room_code else None
    if not room:
        return emit('join_error', {'message': '找不到此房間！請確認代碼是否正確。'})
    if room.get('status') == 'playing':
        return emit('join_error', {'message': '遊戲已經開始，請稍候或加入其他房間！'})

    already_in = any(p['id'] == uid for p in room['players'])
    if not already_in and len(room['players']) >= MAX_PLAYERS:
        return emit('join_error', {'message': '房間已滿！不能再加入了。'})
    if lobby_sids.get(request.sid, (None,))[0] != room_code:
        _leave_previous_room(request.sid, uid)
    join_room(room_code)
    lobby_sids[request.sid] = (room_code, uid)
    if not already_in:
        room['players'].append(_player_info(uid, data.get('user_info')))
    emit('room_updated', _room_payload(room_code), to=room_code)


@socketio.on('leave_room')
def handle_leave_room(data):
    data = data if isinstance(data, dict) else {}
    entry = lobby_sids.pop(request.sid, None)   # 只能讓「自己這個連線」離開，不能把別人踢掉
    if not entry:
        return
    room_code, uid = entry
    leave_room(room_code)
    room = rooms.get(room_code)
    if room and room.get('status') == 'waiting':
        remove_waiting_player(room_code, uid)


@socketio.on('start_game')
def handle_start_game(data):
    entry = lobby_sids.get(request.sid)
    room_code = entry and entry[0]
    room = rooms.get(room_code) if room_code else None
    if not room or room.get('status') != 'waiting':
        return
    if not any(p['id'] == entry[1] for p in room['players']):
        return
    if len(room['players']) < 2:
        return emit('join_error', {'message': '至少要 2 位玩家才能開始。'})

    room['status'] = 'playing'
    player_count = len(room['players'])
    rules = room.get('rules', 1)
    # 💡 啟動後端權威狀態與計時器
    room['game_state'] = init_game_state(room_code, player_count, rules)
    room['game_state']['timer_job'] = gevent.spawn(room_timer_loop, room_code)
    emit('game_started', {'room_code': room_code, 'player_count': player_count, 'rules': rules}, to=room_code)


@socketio.on('spectate_room')
def handle_spectate_room(data):
    """大廳按「觀戰」：只確認房間存在且已開局，真正入房在 game.html 的 join_game_room。"""
    data = data if isinstance(data, dict) else {}
    room_code = v.room_code(data.get('room_code'))
    room = rooms.get(room_code) if room_code else None
    if not room:
        emit('join_error', {'message': '找不到此房間！請確認代碼是否正確。'})
    elif room.get('status') != 'playing':
        emit('join_error', {'message': '這個房間還沒開始對局，可以直接按「加入」入座。'})
    else:
        emit('spectate_ok', {'room_code': room_code, 'player_count': len(room['players']), 'rules': room.get('rules', 1)})
