"""對局頁：入房（含斷線重連）、斷線通知、狀態同步（含棋步驗證）、聊天。"""
import gevent
from flask import request
from flask_socketio import join_room, emit

from server.extensions import socketio
from server.state import rooms, sid_info
from server.engine.game import init_game_state, check_end_game, room_timer_loop, get_clean_state
from server.engine.validate import apply_client_action, restore_state, Invalid
from server.engine.rules import allColors
from server.sockets.rooms import spectator_names, lobby_disconnect, schedule_idle_cleanup
from server.auth_token import verify
from server import validation as v


def seat_color(room, uid):
    """這個玩家在房內是哪個顏色（照入房順序：紅、藍、黃、綠）。"""
    if not uid:
        return None
    if room.get('restored'):
        return next((c for c, u in room.get('seats', {}).items() if u == uid), None)
    for i, p in enumerate(room['players'][:len(allColors)]):
        if p['id'] == uid:
            return allColors[i]
    return None


def claim_restored_seat(room, info, color):
    """伺服器重啟後補回的房間不知道誰坐哪：已登入的玩家可以認領還沒人坐的顏色。"""
    gs = room.get('game_state')
    if not room.get('restored') or not info.get('uid') or not gs or color not in gs['activeColors']:
        return None
    seats = room.setdefault('seats', {})
    if seats.get(color) not in (None, info['uid']) or info['uid'] in [u for c, u in seats.items() if c != color]:
        return None
    seats[color] = info['uid']
    info['color'], info['spectator'] = color, False
    return color


@socketio.on('join_game_room')
def handle_join_game_room(data):
    """進入對局頁（含斷線重連）。玩家拿到自己的顏色，其他人一律當觀戰者。"""
    data = data if isinstance(data, dict) else {}
    room_code = v.room_code(data.get('room_code'))
    if not room_code:
        return
    uid = verify(data.get('token'))
    user_name = v.clean_name(data.get('user_name'), '訪客')
    join_room(room_code)

    room = rooms.get(room_code)
    room_players, current_state, my_color = {}, None, None
    was_known = request.sid in sid_info
    info = {'room': room_code, 'name': user_name, 'spectator': False, 'color': None, 'uid': uid}
    sid_info[request.sid] = info

    if room:
        if room.get('restored'):
            my_color = seat_color(room, uid) or (None if data.get('spectate') else
                                                 claim_restored_seat(room, info, data.get('my_color')))
        else:
            my_color = seat_color(room, uid)
            for i, p in enumerate(room['players'][:len(allColors)]):
                room_players[allColors[i]] = p['name']
        if 'game_state' in room:
            current_state = get_clean_state(room['game_state'])

    info['color'] = my_color
    info['spectator'] = bool(data.get('spectate')) or (room is not None and my_color is None)
    if info['spectator']:
        info['color'] = None
        my_color = None

    emit('init_game', {'my_color': my_color, 'room_players': room_players,
                       'initial_state': current_state, 'spectator': info['spectator']})
    if info['spectator'] and not was_known:
        emit('receive_chat', {'user_name': '系統', 'color': 'yellow', 'message': f'👀 {user_name} 進入觀戰'},
             to=room_code, include_self=False)
    emit('spectators_updated', {'names': spectator_names(room_code)}, to=room_code)


@socketio.on('disconnect')
def handle_disconnect():
    lobby_disconnect(request.sid)
    info = sid_info.pop(request.sid, None)
    if not info:
        return
    room_code = info['room']
    # 讓房內其他人關掉跟這個人的語音連線
    emit('voice_signal', {'from': request.sid, 'type': 'bye'}, to=room_code)
    if info['spectator']:
        emit('spectators_updated', {'names': spectator_names(room_code)}, to=room_code)
    if not any(i['room'] == room_code for i in sid_info.values()):
        schedule_idle_cleanup(room_code)   # 最後一個人離開：一段時間沒人回來就清掉房間


def _reject(reason, state):
    return {'error': reason, 'state': get_clean_state(state) if state else None}


@socketio.on('game_action')
def handle_game_action(data):
    """
    前端把動作後的整盤狀態送上來；伺服器用棋規確認這是「輪到的那位玩家合法的一步」才接受，
    接受後轉發給房內其他人（含觀戰者）。不合法就拒絕，並把伺服器的正確盤面回給送出的人。

    伺服器重啟後房間資料不見時，用第一位送上來的玩家盤面重建（只能做格式檢查），
    之後的每一步照常驗證。
    """
    data = data if isinstance(data, dict) else {}
    room_code = v.room_code(data.get('room_code'))
    info = sid_info.get(request.sid)
    if not room_code or not info or info['room'] != room_code:
        return _reject('請先進入房間', None)
    if info['spectator']:
        return _reject('觀戰中不能下棋', None)
    join_room(room_code)   # 重連後 socket 不在房間裡時補回去

    room = rooms.get(room_code)
    if room is None or 'game_state' not in room:
        # 伺服器重啟：用這位玩家的盤面重建房間
        try:
            state = restore_state(data, init_game_state(room_code, 2, data.get('rules', 1)))
        except Invalid as e:
            return _reject(f'無法還原對局：{e}', None)
        room = rooms[room_code] = {'players': [], 'status': 'playing', 'rules': state['rules'],
                                   'restored': True, 'seats': {}, 'game_state': state}
        if not claim_restored_seat(room, info, info.get('color') or data.get('myColor')):
            del rooms[room_code]
            return _reject('無法確認你的座位，請重新進入房間', None)
        state['version'] = state.get('version', 0) + 1
    else:
        state = room['game_state']
        if room.get('restored'):
            # 補回的房間以認領的座位為準（重啟前記下的顏色不算數）
            actor = seat_color(room, info.get('uid')) or claim_restored_seat(
                room, info, info.get('color') or data.get('myColor'))
        else:
            actor = info.get('color')
        if not actor:
            return _reject('你不是這一局的玩家', state)
        ok, reason = apply_client_action(state, data, actor)
        if not ok:
            return _reject(reason, state)
        state['version'] = state.get('version', 0) + 1

    check_end_game(room_code)

    # 重新開始後計時協程可能已因上一局結束而停止，需要重新啟動
    job = state.get('timer_job')
    if state['phase'] != 'game_over' and (job is None or job.dead):
        state['timer_job'] = gevent.spawn(room_timer_loop, room_code)

    # 操作者本機已經是這個狀態，只轉發給其他人；回送舊狀態給自己反而會在連點時把畫面倒退
    emit('update_board', get_clean_state(state), to=room_code, include_self=False)
    return {'version': state['version']}


@socketio.on('send_chat')
def handle_send_chat(data):
    data = data if isinstance(data, dict) else {}
    info = sid_info.get(request.sid)
    room_code = v.room_code(data.get('room_code'))
    message = data.get('message')
    if not info or info['room'] != room_code or not isinstance(message, str) or not message.strip():
        return
    emit('receive_chat', {
        'user_name': v.clean_name(data.get('user_name'), info['name']),
        'color': data.get('color') if data.get('color') in allColors + ['spectator', 'yellow'] else 'spectator',
        'message': message[:v.CHAT_MAX],
    }, to=room_code, include_self=False)
