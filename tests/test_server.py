"""執行：python tests/test_server.py   （需要先 pip install -r requirements.txt，不需要 MongoDB）
用 Flask-SocketIO 的測試連線模擬兩位玩家＋一位觀戰者，檢查：
建房與規則版本、觀戰、狀態同步（不回送給自己）、語音信令轉送、伺服器重啟後自動補回房間、觀戰者離開。"""
import gevent.monkey
gevent.monkey.patch_all()

import os  # noqa: E402
import sys  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from server.app_factory import create_app  # noqa: E402
from server.extensions import socketio  # noqa: E402
from server.state import rooms  # noqa: E402

app = create_app()
failed = 0


def check(name, ok):
    global failed
    print(f'  {"✓" if ok else "✗"} {name}')
    failed += 0 if ok else 1


def events(client, name):
    return [m['args'][0] for m in client.get_received() if m['name'] == name]


def action(**overrides):
    data = {'room_code': '1234', 'pieces': [], 'walls': [], 'territories': [], 'phase': 'placement',
            'turnIndex': 0, 'movedPieceIndex': -1, 'selectedPieceIndex': -1, 'stepsTaken': 0,
            'moveDir': None, 'rules': 2,
            'playersInfo': {'red': {'hasBreaker': True}, 'blue': {'hasBreaker': True}},
            'playerTimes': {'red': 90, 'blue': 90}}
    data.update(overrides)
    return data


a, b, spec = (socketio.test_client(app) for _ in range(3))

a.emit('create_room', {'room_code': '1234', 'user_info': {'id': 'a', 'name': 'A', 'avatar': 'A'}, 'rules': 2})
check('建房會記住規則 2', events(a, 'room_created')[0]['rules'] == 2)

b.emit('join_room', {'room_code': '1234', 'user_info': {'id': 'b', 'name': 'B', 'avatar': 'B'}})
spec.emit('spectate_room', {'room_code': '1234'})
check('還沒開局不能觀戰', spec.get_received()[-1]['name'] == 'join_error')

a.emit('start_game', {'room_code': '1234'})
check('開局通知帶規則版本', events(b, 'game_started')[0]['rules'] == 2)

a.emit('join_game_room', {'room_code': '1234', 'user_id': 'a', 'user_name': 'A'})
b.emit('join_game_room', {'room_code': '1234', 'user_id': 'b', 'user_name': 'B'})
spec.emit('spectate_room', {'room_code': '1234'})
check('開局後可以觀戰', spec.get_received()[-1]['name'] == 'spectate_ok')

spec.emit('join_game_room', {'room_code': '1234', 'user_id': 'z', 'user_name': 'Zed', 'spectate': True})
received = spec.get_received()
init = [m['args'][0] for m in received if m['name'] == 'init_game'][0]
check('觀戰者被標成 spectator', init['spectator'] is True and init['my_color'] is None)
check('觀戰名單有 Zed', [m['args'][0] for m in received if m['name'] == 'spectators_updated'][-1]['names'] == ['Zed'])

a.get_received(); b.get_received()
ack = a.emit('game_action', action(pieces=[{'color': 'red', 'r': 0, 'c': 0, 'shape': 'circle'}], turnIndex=1), callback=True)
check('送出動作會拿到版本號', ack == {'version': 1})
check('不會把狀態回送給自己', not events(a, 'update_board'))
check('對手收到更新', [s['version'] for s in events(b, 'update_board')] == [1])
check('觀戰者也收到更新', len(events(spec, 'update_board')) == 1)

a.emit('voice_signal', {'room_code': '1234', 'type': 'talk-start', 'data': {'name': 'A'}})
check('語音信令轉送給房內其他人', [v['type'] for v in events(b, 'voice_signal')] == ['talk-start'])

rooms.clear()   # 模擬伺服器重啟把房間弄丟
ack = b.emit('game_action', action(walls=[['1,0', 'blue']], phase='movement'), callback=True)
check('伺服器重啟後用玩家狀態補回房間', ack == {'version': 1} and '1234' in rooms)
check('補回後對手照樣收到更新', len(events(a, 'update_board')) == 1)

spec.disconnect()
check('觀戰者離開後名單清空', events(a, 'spectators_updated')[-1]['names'] == [])

print(f'\n{failed} 個失敗' if failed else '\n全部通過')
sys.exit(1 if failed else 0)
