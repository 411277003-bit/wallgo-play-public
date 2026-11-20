"""大廳房間：建立、加入、離開、開始、觀戰前檢查。"""
import gevent
from flask_socketio import join_room, leave_room, emit

from server.extensions import socketio
from server.state import rooms, sid_info
from server.engine.game import init_game_state, room_timer_loop


@socketio.on('create_room')
def handle_create_room(data):
    room_code = data.get('room_code')
    user_info = data.get('user_info')
    join_room(room_code)
    rules = 2 if data.get('rules') == 2 else 1
    rooms[room_code] = {'players': [user_info], 'status': 'waiting', 'rules': rules}
    emit('room_created', {'room_code': room_code, 'players': rooms[room_code]['players'], 'rules': rules})

@socketio.on('join_room')
def handle_join_room(data):
    room_code = data.get('room_code')
    user_info = data.get('user_info')
    if room_code in rooms:
        if rooms[room_code].get('status') == 'playing':
            emit('join_error', {'message': '遊戲已經開始，請稍候或加入其他房間！'})
            return

        if len(rooms[room_code]['players']) >= 4:
            emit('join_error', {'message': '房間已滿！不能再加入了。'})
        else:
            if not any(p['id'] == user_info['id'] for p in rooms[room_code]['players']):
                join_room(room_code)
                rooms[room_code]['players'].append(user_info)
            emit('room_updated', {'room_code': room_code, 'players': rooms[room_code]['players'],
                                  'rules': rooms[room_code].get('rules', 1)}, to=room_code)
    else:
        emit('join_error', {'message': '找不到此房間！請確認代碼是否正確。'})

@socketio.on('leave_room')
def handle_leave_room(data):
    room_code = data.get('room_code')
    user_id = data.get('user_id')
    if room_code in rooms:
        leave_room(room_code)
        rooms[room_code]['players'] = [p for p in rooms[room_code]['players'] if p['id'] != user_id]
        if len(rooms[room_code]['players']) == 0:
            if 'game_state' in rooms[room_code] and rooms[room_code]['game_state']['timer_job']:
                rooms[room_code]['game_state']['timer_job'].kill()
            del rooms[room_code]
        else:
            emit('room_updated', {'room_code': room_code, 'players': rooms[room_code]['players'],
                                  'rules': rooms[room_code].get('rules', 1)}, to=room_code)

@socketio.on('start_game')
def handle_start_game(data):
    room_code = data.get('room_code')
    if room_code in rooms:
        rooms[room_code]['status'] = 'playing'
        player_count = len(rooms[room_code]['players'])
        
        # 💡 啟動後端權威狀態與計時器
        rules = rooms[room_code].get('rules', 1)
        rooms[room_code]['game_state'] = init_game_state(room_code, player_count, rules)
        rooms[room_code]['game_state']['timer_job'] = gevent.spawn(room_timer_loop, room_code)
        
        emit('game_started', {'room_code': room_code, 'player_count': player_count, 'rules': rules}, to=room_code)


# sid → (room_code, 顯示名稱, 是否觀戰)，斷線時用來通知房內其他人

def spectator_names(room_code):
    return [n for (rc, n, spec) in sid_info.values() if rc == room_code and spec]

@socketio.on('spectate_room')
def handle_spectate_room(data):
    """大廳按「觀戰」：只確認房間存在且已開局，真正入房在 game.html 的 join_game_room。"""
    room_code = data.get('room_code')
    room = rooms.get(room_code)
    if not room:
        emit('join_error', {'message': '找不到此房間！請確認代碼是否正確。'})
    elif room.get('status') != 'playing':
        emit('join_error', {'message': '這個房間還沒開始對局，可以直接按「加入」入座。'})
    else:
        emit('spectate_ok', {'room_code': room_code, 'player_count': len(room['players']), 'rules': room.get('rules', 1)})
