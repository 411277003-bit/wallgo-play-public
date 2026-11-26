"""執行：python tests/test_server.py   （需要先 pip install -r requirements.txt，不需要 MongoDB）
用 Flask-SocketIO 的測試連線模擬玩家與觀戰者，檢查：
建房與規則版本、觀戰、狀態同步（不回送給自己）、語音信令轉送、伺服器重啟後自動補回房間、觀戰者離開；
以及這次加上的：登入 token、房號撞號、清掉沒人的房間、伺服器驗證棋步（擋作弊）、聊天／語音只在房內轉送。"""
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
from server.state import rooms, sid_info, lobby_sids  # noqa: E402
from server.auth_token import issue  # noqa: E402
from server.sockets.rooms import cleanup_if_idle  # noqa: E402

app = create_app()
failed = 0
total = 0


def check(name, ok, detail=''):
    global failed, total
    total += 1
    print(f'  {"✓" if ok else "✗"} {name}' + (f'   ← {detail}' if not ok and detail else ''))
    failed += 0 if ok else 1


def section(title):
    print(f'\n【{title}】')


def events(client, name):
    return [m['args'][0] for m in client.get_received() if m['name'] == name]


def user(uid, name):
    return {'id': uid, 'name': name, 'avatar': name[0]}


def action(**overrides):
    data = {'room_code': '1234', 'pieces': [], 'walls': [], 'territories': [], 'phase': 'placement',
            'turnIndex': 0, 'movedPieceIndex': -1, 'selectedPieceIndex': -1, 'stepsTaken': 0,
            'moveDir': None, 'rules': 2,
            'playersInfo': {'red': {'hasBreaker': True}, 'blue': {'hasBreaker': True}},
            'playerTimes': {'red': 90, 'blue': 90}}
    data.update(overrides)
    return data


TOK = {u: issue(u) for u in ('#a', '#b', '#c', '#z', '#x', '#y')}

# ════════════════════════════════════════════════════════════
section('原有流程')
a, b, spec = (socketio.test_client(app) for _ in range(3))

a.emit('create_room', {'room_code': '1234', 'user_info': user('#a', 'A'), 'rules': 2, 'token': TOK['#a']})
check('建房會記住規則 2', events(a, 'room_created')[0]['rules'] == 2)

b.emit('join_room', {'room_code': '1234', 'user_info': user('#b', 'B'), 'token': TOK['#b']})
spec.emit('spectate_room', {'room_code': '1234'})
check('還沒開局不能觀戰', spec.get_received()[-1]['name'] == 'join_error')

a.emit('start_game', {'room_code': '1234'})
check('開局通知帶規則版本', events(b, 'game_started')[0]['rules'] == 2)

a.emit('join_game_room', {'room_code': '1234', 'token': TOK['#a'], 'user_name': 'A'})
b.emit('join_game_room', {'room_code': '1234', 'token': TOK['#b'], 'user_name': 'B'})
check('玩家用 token 認出自己的顏色', events(a, 'init_game')[0]['my_color'] == 'red'
      and events(b, 'init_game')[0]['my_color'] == 'blue')
spec.emit('spectate_room', {'room_code': '1234'})
check('開局後可以觀戰', spec.get_received()[-1]['name'] == 'spectate_ok')

spec.emit('join_game_room', {'room_code': '1234', 'user_name': 'Zed', 'spectate': True})
received = spec.get_received()
init = [m['args'][0] for m in received if m['name'] == 'init_game'][0]
check('觀戰者被標成 spectator', init['spectator'] is True and init['my_color'] is None)
check('觀戰名單有 Zed', [m['args'][0] for m in received if m['name'] == 'spectators_updated'][-1]['names'] == ['Zed'])

a.get_received(); b.get_received()
ack = a.emit('game_action', action(pieces=[{'color': 'red', 'r': 0, 'c': 0, 'shape': 'circle'}], turnIndex=1), callback=True)
check('送出合法動作會拿到版本號', ack == {'version': 1}, ack)
check('不會把狀態回送給自己', not events(a, 'update_board'))
check('對手收到更新', [s['version'] for s in events(b, 'update_board')] == [1])
check('觀戰者也收到更新', len(events(spec, 'update_board')) == 1)

a.emit('voice_signal', {'room_code': '1234', 'type': 'talk-start', 'data': {'name': 'A'}})
check('語音信令轉送給房內其他人', [v['type'] for v in events(b, 'voice_signal')] == ['talk-start'])

# ════════════════════════════════════════════════════════════
section('棋步驗證（擋作弊）')
spec.get_received()
ack = a.emit('game_action', action(pieces=[{'color': 'red', 'r': 0, 'c': 0, 'shape': 'circle'},
                                           {'color': 'blue', 'r': 2, 'c': 2, 'shape': 'circle'}], turnIndex=2), callback=True)
check('紅色替藍色下棋 → 拒絕', 'error' in ack, ack)
check('拒絕時附上伺服器的正確盤面', ack.get('state', {}).get('version') == 1 and len(ack['state']['pieces']) == 1)
check('被拒絕的動作不會轉發給對手', not events(b, 'update_board'))
ack = b.emit('game_action', action(pieces=[{'color': 'red', 'r': 0, 'c': 0, 'shape': 'circle'}] +
                                   [{'color': 'blue', 'r': 2 * i, 'c': 12, 'shape': 'circle'} for i in range(7)] * 70,
                                   turnIndex=2), callback=True)
check('一次送 500 顆棋子 → 拒絕（以前照單全收）', 'error' in ack, ack)
ack = b.emit('game_action', action(walls=[['abc', 'red']]), callback=True)
check('牆壁座標亂填 → 拒絕，伺服器沒有當掉（以前拋 ValueError）', 'error' in ack, ack)
ack = spec.emit('game_action', action(pieces=[{'color': 'red', 'r': 0, 'c': 0, 'shape': 'circle'},
                                              {'color': 'blue', 'r': 2, 'c': 2, 'shape': 'circle'}], turnIndex=2), callback=True)
check('觀戰者不能下棋', 'error' in ack, ack)
ack = b.emit('game_action', action(pieces=[{'color': 'red', 'r': 0, 'c': 0, 'shape': 'circle'},
                                           {'color': 'blue', 'r': 2, 'c': 2, 'shape': 'circle'}], turnIndex=2), callback=True)
check('藍色下自己的棋 → 接受', ack == {'version': 2}, ack)
check('伺服器盤面是 2 顆棋', len(rooms['1234']['game_state']['pieces']) == 2)

# ════════════════════════════════════════════════════════════
section('伺服器重啟後補回房間')
rooms.clear()   # 模擬伺服器重啟把房間弄丟
a.get_received()
ack = b.emit('game_action', action(walls=[['1,0', 'blue']], phase='movement'), callback=True)
check('伺服器重啟後用玩家狀態補回房間', ack == {'version': 1} and '1234' in rooms, ack)
check('補回的房間記得送出者坐藍色', rooms['1234']['seats'] == {'blue': '#b'})
check('補回後對手照樣收到更新', len(events(a, 'update_board')) == 1)
ack = a.emit('game_action', action(walls=[['1,0', 'blue'], ['3,0', 'red']], phase='movement'), callback=True)
check('紅色（原本的玩家）可以認領紅色座位', rooms['1234']['seats'].get('red') == '#a')
check('認領後照樣驗證棋步（沒有棋子卻蓋牆 → 拒絕）', 'error' in ack, ack)
z = socketio.test_client(app)
z.emit('join_game_room', {'room_code': '1234', 'token': TOK['#z'], 'user_name': 'Z', 'my_color': 'blue'})
check('別人不能搶走已經有人認領的座位', events(z, 'init_game')[0]['my_color'] is None)
z.disconnect()

# ════════════════════════════════════════════════════════════
section('聊天與語音只在房內轉送')
a.get_received(); b.get_received()   # 清掉前面 Z 進出房間的通知
outsider = socketio.test_client(app)
outsider.emit('send_chat', {'room_code': '1234', 'user_name': 'X', 'color': 'red', 'message': 'spam'})
check('沒進房間的人不能在房內聊天', not events(a, 'receive_chat'))
b.emit('send_chat', {'room_code': '1234', 'user_name': 'B', 'color': 'blue', 'message': 'x' * 5000})
msgs = events(a, 'receive_chat')
check('聊天訊息超過 300 字會被截斷', len(msgs) == 1 and len(msgs[0]['message']) == 300)
other_room = socketio.test_client(app)
other_room.emit('join_game_room', {'room_code': '5555', 'user_name': 'O', 'spectate': True})
other_sid = next(s for s, i in sid_info.items() if i['room'] == '5555')
other_room.get_received()
a.emit('voice_signal', {'room_code': '1234', 'type': 'offer', 'data': {}, 'to': other_sid})
check('語音信令不能指定送給別的房間的人', not events(other_room, 'voice_signal'))
outsider.emit('voice_signal', {'room_code': '1234', 'type': 'offer', 'data': {}})
check('沒進房間的人不能送語音信令', not events(b, 'voice_signal'))
other_room.disconnect(); outsider.disconnect()

spec.disconnect()
check('觀戰者離開後名單清空', events(a, 'spectators_updated')[-1]['names'] == [])

# ════════════════════════════════════════════════════════════
section('登入 token 與房號')
x = socketio.test_client(app)
x.emit('create_room', {'room_code': '7777', 'user_info': user('#x', 'X')})
check('沒有 token 不能建房', events(x, 'join_error') and '7777' not in rooms)
x.emit('join_room', {'room_code': '1234', 'user_info': user('#a', 'A'), 'token': 'forged'})
check('偽造 token 不能入房', events(x, 'join_error'))
x.emit('create_room', {'room_code': '7777', 'user_info': user('#a', 'Fake'), 'token': TOK['#x']})
check('user_info 寫別人的 ID 也沒用：房內記的是 token 的 ID', rooms['7777']['players'][0]['id'] == '#x')
y = socketio.test_client(app)
y.emit('create_room', {'room_code': '7777', 'user_info': user('#y', 'Y'), 'token': TOK['#y']})
first_code = events(y, 'room_created')[0]['room_code']
check('房號撞到別人的房間 → 自動換一個（以前會把對方踢掉）',
      first_code != '7777' and rooms['7777']['players'][0]['id'] == '#x' and rooms[first_code]['players'][0]['id'] == '#y')
y.emit('join_room', {'room_code': '7777', 'user_info': None, 'token': TOK['#y']})
check('user_info 是 null 也不會當掉（以前拋 TypeError）', [p['id'] for p in rooms['7777']['players']] == ['#x', '#y'])
check('建了房又去加入別人的房 → 原本的空房間清掉', first_code not in rooms)
y.emit('leave_room', {'room_code': '7777', 'user_id': '#x'})
check('leave_room 只能讓自己離開，不能踢掉別人', [p['id'] for p in rooms['7777']['players']] == ['#x'])
y.emit('create_room', {'room_code': 'abcd', 'user_info': user('#y', 'Y'), 'token': TOK['#y']})
y_code = events(y, 'room_created')[0]['room_code']
check('房號格式不對 → 伺服器自己產生 4 位數房號', y_code.isdigit() and len(y_code) == 4 and y_code != '7777')
x.emit('start_game', {'room_code': y_code})
check('不能替別人的房間開局（start_game 只看自己所在的房間）', rooms[y_code]['status'] == 'waiting')
check('只有 1 個人時不能開局', rooms['7777']['status'] == 'waiting' and events(x, 'join_error'))

# ════════════════════════════════════════════════════════════
section('清掉沒人的房間（記憶體洩漏）')
y.disconnect()
check('建房者直接關網頁 → 房間刪除（以前永遠留在記憶體）', y_code not in rooms)
w = socketio.test_client(app)
w.emit('join_room', {'room_code': '7777', 'user_info': user('#y', 'Y'), 'token': TOK['#y']})
x.get_received()
w.disconnect()
check('等待室裡有人關網頁 → 從名單移除並通知其他人', [p['id'] for p in rooms['7777']['players']] == ['#x']
      and [p['id'] for p in events(x, 'room_updated')[-1]['players']] == ['#x'])
x.disconnect()
check('最後一個人也離開 → 房間刪除', '7777' not in rooms)

a.disconnect(); b.disconnect()
check('對局中所有人斷線後，房間還在（給 60 秒重連）', '1234' in rooms)
check('60 秒後沒人回來 → 清掉房間並停掉計時器', cleanup_if_idle('1234') and '1234' not in rooms)
check('所有連線資料都清乾淨', not sid_info and not lobby_sids, f'{sid_info} {lobby_sids}')

print(f'\n共 {total} 項，{failed} 個失敗' if failed else f'\n全部 {total} 項通過')
sys.exit(1 if failed else 0)
