"""封包測試：python tests/packet_report.py [--games 10] [--remote https://wallgo-play.onrender.com]

在本機開一個真的後端，用兩個機器人玩家實際下完幾局，量：
  A. 封包大小：每種封包（送出動作、伺服器確認、盤面更新、計時同步）幾 bytes，牆越多封包越大
  B. 往返時間（RTT）：送出 game_action 到收到確認，沒有其他負載時的分布
  C. 計時同步的穩定度：伺服器每秒送一次 sync_time，實際間隔的平均與抖動
  D. 斷線重連：故意斷線再連回來，多久能重新入房並拿到正確盤面
  E. 作弊封包：送 6 種竄改過的封包，伺服器怎麼回應
  F.（加 --remote）實際網路：到雲端後端的 HTTP 往返時間與 WebSocket 連線時間
結果存到 tests/packet_results.json。
"""
import argparse
import json
import os
import random
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stress_test import ROOT, SECRET, SERVER_CODE, pct, to_client  # noqa: E402  (也設定好 SECRET_KEY)

import socketio  # noqa: E402
from server.auth_token import issue  # noqa: E402
from server.engine.validate import legal_next_states, current_color, _fresh_state  # noqa: E402
from server.engine.rules import check_game_over  # noqa: E402

size = lambda obj: len(json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode())  # noqa: E731


def stats(xs, unit=''):
    if not xs:
        return {}
    return {'n': len(xs), 'mean': round(statistics.mean(xs), 2), 'p50': round(pct(xs, 50), 2),
            'p95': round(pct(xs, 95), 2), 'max': round(max(xs), 2), 'min': round(min(xs), 2),
            'stdev': round(statistics.stdev(xs), 2) if len(xs) > 1 else 0}


class Player:
    def __init__(self, url, uid):
        self.url, self.uid, self.token = url, uid, issue(uid)
        self.sio = socketio.Client(reconnection=False)
        self.inbox = {}
        self.cv = threading.Condition()
        self.recv_sizes = []      # (事件名稱, bytes)
        self.ticks = []
        self.state = self.color = self.room = None
        for name in ('room_created', 'room_updated', 'game_started', 'init_game', 'join_error'):
            self.sio.on(name, self._store(name))
        self.sio.on('update_board', self._on_update)
        self.sio.on('sync_time', self._on_tick)

    def _store(self, name):
        def h(data):
            with self.cv:
                self.inbox[name] = data
                self.cv.notify_all()
        return h

    def _on_update(self, data):
        self.recv_sizes.append(('update_board', size(data)))
        self.state = data
        with self.cv:
            self.inbox['update_board'] = data
            self.cv.notify_all()

    def _on_tick(self, data):
        self.ticks.append(time.perf_counter())
        self.recv_sizes.append(('sync_time', size(data)))

    def wait(self, name, timeout=10):
        with self.cv:
            ok = self.cv.wait_for(lambda: name in self.inbox, timeout)
            if not ok:
                raise TimeoutError(f'等不到 {name}')
            return self.inbox.pop(name)

    def connect(self):
        self.sio.connect(self.url, transports=['websocket'], wait_timeout=10)

    def join_game(self):
        self.sio.emit('join_game_room', {'room_code': self.room, 'token': self.token, 'user_name': self.uid,
                                         'my_color': self.color})
        init = self.wait('init_game')
        self.color = init['my_color'] or self.color
        self.state = init['initial_state']
        return init

    def emit_ack(self, data, timeout=10):
        box, ev = {}, threading.Event()
        t0 = time.perf_counter()

        def cb(ack):
            box['ack'], box['ms'] = ack, (time.perf_counter() - t0) * 1000
            ev.set()
        self.sio.emit('game_action', data, callback=cb)
        if not ev.wait(timeout):
            return None, None
        return box['ack'], box['ms']


def start_server(port):
    proc = subprocess.Popen([sys.executable, '-c', SERVER_CODE.format(root=ROOT, port=port)],
                            env={**os.environ, 'SECRET_KEY': SECRET}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f'http://127.0.0.1:{port}'
    for _ in range(100):
        try:
            p = socketio.Client(); p.connect(url, transports=['websocket'], wait_timeout=2); p.disconnect()
            return proc, url
        except Exception:  # noqa: BLE001
            time.sleep(0.2)
    proc.terminate()
    raise RuntimeError('後端沒有啟動')


def setup_room(url, rules):
    red, blue = Player(url, '#pr' + uuid.uuid4().hex[:8]), Player(url, '#pb' + uuid.uuid4().hex[:8])
    red.connect(); blue.connect()
    red.sio.emit('create_room', {'room_code': '1000', 'token': red.token, 'user_info': {'name': 'R'}, 'rules': rules})
    code = red.wait('room_created')['room_code']
    blue.sio.emit('join_room', {'room_code': code, 'token': blue.token, 'user_info': {'name': 'B'}})
    blue.wait('room_updated')
    red.sio.emit('start_game', {})
    red.wait('game_started'); blue.wait('game_started')
    for p in (red, blue):
        p.room = code
        p.join_game()
    return red, blue


def restart(red, blue):
    s = red.state
    gid = uuid.uuid4().hex
    ack, _ = red.emit_ack({'room_code': red.room, 'phase': 'placement', 'pieces': [], 'walls': [], 'gameId': gid})
    nxt = {**s}; _fresh_state(nxt, gid)
    red.state = blue.state = {**nxt, 'version': ack['version']}


def play(red, blue, games, rng, think=0.05, max_actions=None):
    """兩位機器人輪流下，直到下完指定局數（或下了 max_actions 步）。回傳每一個動作的紀錄。"""
    log = []
    by_color = {red.color: red, blue.color: blue}
    finished = 0
    while finished < games and (max_actions is None or len(log) < max_actions):
        s = red.state
        if s['phase'] == 'game_over':
            finished += 1
            if finished >= games:
                break
            gid = uuid.uuid4().hex
            ack, ms = red.emit_ack({'room_code': red.room, 'phase': 'placement', 'pieces': [], 'walls': [], 'gameId': gid})
            nxt = {**s}; _fresh_state(nxt, gid)
            red.state = blue.state = {**nxt, 'version': ack['version']}
            continue
        cc = current_color(s)
        actor, other = by_color[cc], (blue if by_color[cc] is red else red)
        options = legal_next_states(s, cc)
        nxt = rng.choice(options)
        data = {**to_client({**s, **nxt}), 'room_code': actor.room}
        other.inbox.pop('update_board', None)
        t0 = time.perf_counter()
        ack, ms = actor.emit_ack(data)
        upd = other.wait('update_board')
        bcast_ms = (time.perf_counter() - t0) * 1000
        log.append({'phase': s['phase'], 'walls': len(s['walls']), 'send_bytes': size(data),
                    'ack_bytes': size(ack), 'ack_ms': ms, 'bcast_ms': bcast_ms, 'accepted': 'error' not in ack})
        new = {**s, **nxt, 'version': ack['version'], 'territories': upd.get('territories')}
        if new['phase'] != 'placement' and check_game_over(new)['over']:
            new['phase'] = 'game_over'
        red.state = blue.state = upd if upd.get('phase') == 'game_over' else new
        time.sleep(think)
    return log


def reconnect_test(url, red, blue, times=10):
    """藍色玩家故意斷線再連回來：量重新入房、拿到盤面的時間，並確認盤面跟伺服器一致。"""
    out = []
    for _ in range(times):
        blue.sio.disconnect()
        time.sleep(0.3)
        t0 = time.perf_counter()
        blue.sio = socketio.Client(reconnection=False)
        for name in ('init_game', 'join_error'):
            blue.sio.on(name, blue._store(name))
        blue.sio.on('update_board', blue._on_update)
        blue.sio.on('sync_time', blue._on_tick)
        blue.connect()
        init = blue.join_game()
        ms = (time.perf_counter() - t0) * 1000
        same = init['initial_state']['pieces'] == red.state['pieces'] and init['my_color'] == blue.color
        out.append({'ms': round(ms, 1), 'state_ok': same})
    return out


def cheat_test(red, blue):
    """輪到的人送竄改過的封包，記錄伺服器的回應。"""
    s = red.state if current_color(red.state) == red.color else blue.state
    actor = red if current_color(s) == red.color else blue
    other = blue if actor is red else red
    base = {**to_client(s), 'room_code': actor.room}
    cases = []

    def attempt(label, sender, data):
        ack, ms = sender.emit_ack(data)
        cases.append({'case': label, 'accepted': bool(ack) and 'error' not in ack,
                      'reply': (ack or {}).get('error', 'accepted'), 'ms': round(ms or -1, 1),
                      'resync_bytes': size(ack.get('state')) if ack and ack.get('state') else 0})

    d = json.loads(json.dumps(base)); d['pieces'].append({'color': actor.color, 'r': 6, 'c': 6}); attempt('憑空多放一顆棋', actor, d)
    d = json.loads(json.dumps(base)); d['walls'] = []; attempt('把場上的牆全部拆掉', actor, d)
    d = json.loads(json.dumps(base)); d['pieces'][0]['r'] = (d['pieces'][0]['r'] + 6) % 14 // 2 * 2; attempt('棋子瞬移', actor, d)
    d = json.loads(json.dumps(base)); d['turnIndex'] = (d['turnIndex'] + 1) % 2; attempt('跳過自己的回合', actor, d)
    d = json.loads(json.dumps(base)); d['playersInfo'] = {c: {'hasBreaker': True} for c in d['playersInfo']}; d['phase'] = 'wall_breaking'
    attempt('破牆權用完又改回來', actor, d)
    attempt('不是自己的回合卻送棋步', other, {**json.loads(json.dumps(base)), 'room_code': other.room})
    return cases


def remote_test(base_url, n=20):
    out = {'url': base_url, 'http_ms': [], 'ws_connect_ms': [], 'errors': 0}
    for i in range(n):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(f'{base_url}/api/global_stats', timeout=60) as r:
                r.read()
            out['http_ms'].append((time.perf_counter() - t0) * 1000)
        except Exception:  # noqa: BLE001
            out['errors'] += 1
        time.sleep(0.3)
    for i in range(5):
        c = socketio.Client(reconnection=False)
        t0 = time.perf_counter()
        try:
            c.connect(base_url, transports=['websocket'], wait_timeout=30)
            out['ws_connect_ms'].append((time.perf_counter() - t0) * 1000)
            c.disconnect()
        except Exception:  # noqa: BLE001
            out['errors'] += 1
        time.sleep(0.5)
    # 純 WebSocket 往返：送一個不存在的房號給 spectate_room，伺服器不查資料庫、立刻回 join_error
    out['ws_rtt_ms'] = []
    c = socketio.Client(reconnection=False)
    got = threading.Event()
    c.on('join_error', lambda d: got.set())
    try:
        c.connect(base_url, transports=['websocket'], wait_timeout=30)
        for i in range(30):
            got.clear()
            t0 = time.perf_counter()
            c.emit('spectate_room', {'room_code': '0000'})
            if got.wait(10):
                out['ws_rtt_ms'].append((time.perf_counter() - t0) * 1000)
            else:
                out['errors'] += 1
            time.sleep(0.2)
        c.disconnect()
    except Exception:  # noqa: BLE001
        out['errors'] += 1
    out['ws_rtt'] = stats(out['ws_rtt_ms'])
    del out['ws_rtt_ms']
    out['first_http_ms'] = round(out['http_ms'][0], 1) if out['http_ms'] else None
    out['http'] = stats(out['http_ms'][1:])   # 第一次可能是冷啟動，分開看
    out['ws_connect'] = stats(out['ws_connect_ms'])
    del out['http_ms'], out['ws_connect_ms']
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--games', type=int, default=10)
    ap.add_argument('--port', type=int, default=5066)
    ap.add_argument('--remote', default=None, help='雲端後端網址，例如 https://wallgo-play.onrender.com')
    ap.add_argument('--out', default=os.path.join(ROOT, 'tests', 'packet_results.json'))
    args = ap.parse_args()
    rng = random.Random(2026)
    res = {}
    proc, url = start_server(args.port)
    try:
        red, blue = setup_room(url, rules=1)
        print(f'▶ A/B. 兩位玩家下 {args.games} 局…', flush=True)
        t0 = time.perf_counter()
        log = play(red, blue, args.games, rng)
        res['game_seconds'] = round(time.perf_counter() - t0, 1)
        res['actions'] = len(log)
        res['accepted'] = sum(x['accepted'] for x in log)
        res['send_bytes'] = stats([x['send_bytes'] for x in log])
        res['send_bytes_by_phase'] = {ph: stats([x['send_bytes'] for x in log if x['phase'] == ph])
                                      for ph in ('placement', 'movement', 'wall_building', 'wall_breaking')
                                      if any(x['phase'] == ph for x in log)}
        buckets = {}
        for x in log:
            buckets.setdefault(min(x['walls'] // 10 * 10, 60), []).append(x['send_bytes'])
        res['send_bytes_by_walls'] = {f'{k}~{k + 9}道牆' if k < 60 else '60道以上': round(statistics.mean(v))
                                      for k, v in sorted(buckets.items())}
        res['ack_bytes'] = stats([x['ack_bytes'] for x in log])
        recv = blue.recv_sizes + red.recv_sizes
        res['update_board_bytes'] = stats([b for n, b in recv if n == 'update_board'])
        res['sync_time_bytes'] = stats([b for n, b in recv if n == 'sync_time'])
        res['ack_rtt_ms'] = stats([x['ack_ms'] for x in log])
        res['broadcast_ms'] = stats([x['bcast_ms'] for x in log])
        print(f'  {len(log)} 個動作，全部接受：{res["accepted"] == len(log)}')

        # 後面的測試要在「對局進行中」做：重新開一局，下到移動期、場上有幾道牆
        restart(red, blue)
        play(red, blue, 1, rng, max_actions=30)
        print('▶ C. 計時同步間隔（聽 30 秒）…', flush=True)
        red.ticks.clear()
        time.sleep(30.5)
        iv = [(b - a) * 1000 for a, b in zip(red.ticks, red.ticks[1:])]
        res['sync_interval_ms'] = {**stats(iv), 'over_1500ms': sum(x > 1500 for x in iv)}

        print('▶ D. 斷線重連 10 次…', flush=True)
        rc = reconnect_test(url, red, blue)
        res['reconnect_ms'] = {**stats([x['ms'] for x in rc]), 'state_ok': sum(x['state_ok'] for x in rc)}

        print('▶ E. 作弊封包…', flush=True)
        res['cheat'] = cheat_test(red, blue)
        for p in (red, blue):
            p.sio.disconnect()
    finally:
        proc.terminate(); proc.wait(10)

    if args.remote:
        print(f'▶ F. 實際網路：{args.remote} …', flush=True)
        res['remote'] = remote_test(args.remote.rstrip('/'))

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print(f'\n結果已存到 {args.out}')


if __name__ == '__main__':
    main()
