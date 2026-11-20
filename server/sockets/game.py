"""對局頁：入房（含斷線重連）、斷線通知、狀態同步、聊天。"""
import gevent
from flask import request
from flask_socketio import join_room, emit

from server.extensions import socketio
from server.state import rooms, sid_info
from server.engine.game import init_game_state, check_end_game, room_timer_loop, get_clean_state
from server.sockets.rooms import spectator_names


@socketio.on('join_game_room')
def handle_join_game_room(data):
    """進入對局頁（含斷線重連）。玩家拿到自己的顏色，其他人一律當觀戰者。"""
    room_code = data.get('room_code')
    user_id = data.get('user_id')
    user_name = data.get('user_name') or '訪客'
    join_room(room_code)

    my_color = None
    room_players = {}
    current_state = None

    if room_code in rooms:
        colors = ['red', 'blue', 'yellow', 'green']
        for i, p in enumerate(rooms[room_code]['players']):
            if i < len(colors):
                room_players[colors[i]] = p['name']
                if p['id'] == user_id:
                    my_color = colors[i]
        if 'game_state' in rooms[room_code]:
            current_state = get_clean_state(rooms[room_code]['game_state'])

    is_spectator = bool(data.get('spectate')) or (room_code in rooms and my_color is None)
    was_known = request.sid in sid_info
    sid_info[request.sid] = (room_code, user_name, is_spectator)

    emit('init_game', {'my_color': my_color, 'room_players': room_players,
                       'initial_state': current_state, 'spectator': is_spectator})
    if is_spectator and not was_known:
        emit('receive_chat', {'user_name': '系統', 'color': 'yellow', 'message': f'👀 {user_name} 進入觀戰'},
             to=room_code, include_self=False)
    emit('spectators_updated', {'names': spectator_names(room_code)}, to=room_code)

@socketio.on('disconnect')
def handle_disconnect():
    info = sid_info.pop(request.sid, None)
    if not info:
        return
    room_code, user_name, is_spectator = info
    # 讓房內其他人關掉跟這個人的語音連線
    emit('voice_signal', {'from': request.sid, 'type': 'bye'}, to=room_code)
    if is_spectator:
        emit('spectators_updated', {'names': spectator_names(room_code)}, to=room_code)


@socketio.on('game_action')
def handle_game_action(data):
    """
    前端把動作後的整盤狀態送上來，後端更新後轉發給房內其他人（含觀戰者）。
    伺服器重啟、或連線斷掉重連後，房間資料／socket 房間成員都可能不見，這裡一併自我修復，
    否則對方的棋步會一直收不到。
    """
    room_code = data.get('room_code')
    if not room_code:
        return
    join_room(room_code)   # 重連後 socket 不在房間裡時補回去

    room = rooms.setdefault(room_code, {'players': [], 'status': 'playing'})
    if 'game_state' not in room:
        room['game_state'] = init_game_state(room_code, len(data.get('playersInfo') or {}) or 2, data.get('rules', 1))
        room['status'] = 'playing'
    state = room['game_state']

    state['pieces'] = data.get('pieces', [])
    state['walls'] = [{'r': int(k.split(',')[0]), 'c': int(k.split(',')[1]), 'color': v} for k, v in data.get('walls', [])]
    state['territories'] = data.get('territories', [])
    state['phase'] = data.get('phase')
    state['turnIndex'] = data.get('turnIndex')
    state['movedPieceIndex'] = data.get('movedPieceIndex')
    state['selectedPieceIndex'] = data.get('selectedPieceIndex')
    state['stepsTaken'] = data.get('stepsTaken')
    state['moveDir'] = data.get('moveDir')
    if data.get('rules') in (1, 2):
        state['rules'] = data['rules']
    state['playersInfo'] = data.get('playersInfo', state['playersInfo'])
    state['playerTimes'] = data.get('playerTimes', state['playerTimes'])
    if data.get('activeColors'):
        state['activeColors'] = data['activeColors']
        state['placementQueue'] = data.get('placementQueue', state['placementQueue'])
        state['movementOrder'] = data.get('movementOrder', state['movementOrder'])
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
    room_code = data.get('room_code')
    emit('receive_chat', data, to=room_code, include_self=False)
