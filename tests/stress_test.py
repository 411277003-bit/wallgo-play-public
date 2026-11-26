"""壓力測試：python tests/stress_test.py [--rooms 10,50,100,200] [--seconds 15]

在本機開一個真的後端（另一個程序、gevent、WebSocket），用機器人玩家同時開很多房間「真的下棋」：
每間房 2 位玩家，輪到自己就從合法棋步裡隨機挑一步送出（伺服器會驗證），下完一局就重新開始。
每個等級量：
  - 動作確認延遲：送出 game_action 到收到伺服器 ack 的時間（含伺服器驗證棋步）
  - 廣播延遲：一方送出到「對手收到 update_board」的時間（玩家實際感受到的延遲）
  - 吞吐量（每秒處理幾個動作）、被拒絕／逾時的動作數、伺服器記憶體
另外量：
  - 房號撞號：故意 300 次都要同一個房號，確認每次都分到不同房間
  - 逾時代打（force_ai_move）的運算時間：gevent 是單執行緒，這段算越久，所有房間卡越久

不需要 MongoDB（只用到 Socket.IO）。結果另存 tests/stress_results.json，可以拿去畫圖。
注意：這是本機測試（沒有網路延遲），量的是「伺服器本身的處理能力」；機器人客戶端也在同一台電腦上，
房間數很多時客戶端自己也會吃 CPU，數字會比真實情況保守（偏慢）。
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
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

SECRET = 'stress-test-secret-' + uuid.uuid4().hex
os.environ['SECRET_KEY'] = SECRET          # 讓這個程序簽的 token 伺服器認得

import socketio  # noqa: E402  (python-socketio 客戶端)
from server.auth_token import issue  # noqa: E402
from server.engine.validate import legal_next_states, current_color, _fresh_state  # noqa: E402
from server.engine.rules import check_game_over  # noqa: E402

SERVER_CODE = '''
import gevent.monkey; gevent.monkey.patch_all()
import sys, logging; sys.path.insert(0, {root!r})
sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')
logging.getLogger('werkzeug').setLevel(logging.ERROR)
from server.app_factory import create_app
from server.extensions import socketio
app = create_app()
socketio.run(app, host='127.0.0.1', port={port}, debug=False, log_output=False)
'''


def server_memory_mb(pid):
    try:
        import psutil
        return psutil.Process(pid).memory_info().rss / 2**20
    except ImportError:
        pass
    try:
        if os.name == 'nt':
            out = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
                                 capture_output=True, text=True).stdout
            return int(out.strip().split('","')[-1].strip('"').replace(',', '').split()[0]) / 1024
        with open(f'/proc/{pid}/status') as f:
            return next(int(line.split()[1]) for line in f if line.startswith('VmRSS')) / 1024
    except Exception:  # noqa: BLE001
        return float('nan')


def pct(values, p):
    if not values:
        return float('nan')
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p / 100))]


def to_client(s):
    return {
        'pieces': s['pieces'], 'walls': [[f"{w['r']},{w['c']}", w['color']] for w in s['walls']],
        'phase': s['phase'], 'turnIndex': s['turnIndex'], 'selectedPieceIndex': s['selectedPieceIndex'],
        'movedPieceIndex': s['movedPieceIndex'], 'stepsTaken': s['stepsTaken'], 'moveDir': s.get('moveDir'),
        'playersInfo': s['playersInfo'], 'playerTimes': s['playerTimes'], 'rules': s['rules'],
        'activeColors': s['activeColors'], 'placementQueue': s['placementQueue'],
        'movementOrder': s['movementOrder'], 'gameId': s.get('gameId'),
    }


class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.ack_ms, self.bcast_ms = [], []
        self.accepted = self.rejected = self.timeouts = self.games = 0

    def add(self, **kw):
        with self.lock:
            for k, v in kw.items():
                if isinstance(getattr(self, k), list):
                    getattr(self, k).append(v)
                else:
                    setattr(self, k, getattr(self, k) + v)


class Bot:
    """一位機器人玩家：連線、入房、輪到自己就下一步合法的棋。"""

    def __init__(self, url, uid, stats, room_sent, rng, think):
        self.url, self.uid, self.stats, self.room_sent, self.rng, self.think = url, uid, stats, room_sent, rng, think
        self.token = issue(uid)
        self.sio = socketio.Client(reconnection=False)
        self.state, self.color, self.room = None, None, None
        self.events = {}
        self.busy = False
        for name in ('room_created', 'room_updated', 'game_started', 'init_game', 'join_error'):
            self.sio.on(name, self._waiter(name))
        self.sio.on('update_board', self._on_update)

    def _waiter(self, name):
        ev = self.events.setdefault(name, [threading.Event(), None])

        def handler(data):
            ev[1] = data
            ev[0].set()
        return handler

    def wait(self, name, timeout=20):
        ev = self.events[name]
        if not ev[0].wait(timeout):
            raise TimeoutError(f'{self.uid} 等不到 {name}')
        ev[0].clear()
        return ev[1]

    def _on_update(self, data):
        sent = self.room_sent.get(self.room)
        if sent:
            self.stats.add(bcast_ms=(time.perf_counter() - sent) * 1000)
        self.state = data

    def connect(self):
        self.sio.connect(self.url, transports=['websocket'], wait_timeout=20)

    def step(self):
        """輪到自己就下一步；回傳是否有送出。"""
        s = self.state
        if self.busy or not s or not self.sio.connected:
            return False
        if s['phase'] == 'game_over':
            if self.color != 'red':
                return False
            gid = uuid.uuid4().hex
            data = {'phase': 'placement', 'pieces': [], 'walls': [], 'gameId': gid}
            nxt = {**s}
            _fresh_state(nxt, gid)          # 跟伺服器一樣把盤面歸零
            self.stats.add(games=1)
        else:
            if current_color(s) != self.color:
                return False
            options = legal_next_states(s, self.color)
            if not options:
                return False
            nxt = self.rng.choice(options)
            data = to_client({**s, **nxt})
        data['room_code'] = self.room
        self.busy = True
        t0 = time.perf_counter()
        self.room_sent[self.room] = t0
        done = threading.Event()

        def on_ack(ack):
            self.stats.add(ack_ms=(time.perf_counter() - t0) * 1000)
            if ack and 'error' not in ack:
                self.stats.add(accepted=1)
                new = {**s, **nxt, 'version': ack['version']}
                # 跟真的前端一樣：自己下完後自己判斷是否結束（伺服器不會把狀態回送給送出的人）
                if new['phase'] != 'placement' and check_game_over(new)['over']:
                    new['phase'] = 'game_over'
                self.state = new
            else:
                self.stats.add(rejected=1)
                if ack and ack.get('state'):
                    self.state = ack['state']
            done.set()

        self.sio.emit('game_action', data, callback=on_ack)

        def watchdog():
            if not done.wait(5):
                self.stats.add(timeouts=1)
            self.busy = False
        threading.Thread(target=watchdog, daemon=True).start()
        return True

    def close(self):
        try:
            self.sio.disconnect()
        except Exception:  # noqa: BLE001
            pass


def run_level(url, n_rooms, seconds, think, rng, server_pid):
    stats, room_sent = Stats(), {}
    bots = []
    t_setup = time.perf_counter()
    for i in range(n_rooms):
        red = Bot(url, f'#r{n_rooms}x{i}', stats, room_sent, random.Random(rng.random()), think)
        blue = Bot(url, f'#b{n_rooms}x{i}', stats, room_sent, random.Random(rng.random()), think)
        red.connect(); blue.connect()
        red.sio.emit('create_room', {'room_code': f'{rng.randint(1000, 9999)}', 'token': red.token,
                                     'user_info': {'name': 'R'}, 'rules': rng.choice([1, 2])})
        code = red.wait('room_created')['room_code']
        blue.sio.emit('join_room', {'room_code': code, 'token': blue.token, 'user_info': {'name': 'B'}})
        blue.wait('room_updated')
        red.sio.emit('start_game', {})
        red.wait('game_started'); blue.wait('game_started')
        for bot in (red, blue):
            bot.room = code
            bot.sio.emit('join_game_room', {'room_code': code, 'token': bot.token, 'user_name': bot.uid})
            init = bot.wait('init_game')
            bot.color, bot.state = init['my_color'], init['initial_state']
        bots += [red, blue]
    setup_s = time.perf_counter() - t_setup
    mem_before = server_memory_mb(server_pid)

    stop = time.perf_counter() + seconds
    t_start = time.perf_counter()

    def loop(bot):
        while time.perf_counter() < stop:
            bot.step()
            time.sleep(bot.think * (0.5 + bot.rng.random()))
    threads = [threading.Thread(target=loop, args=(b,), daemon=True) for b in bots]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t_start
    time.sleep(1)
    mem_after = server_memory_mb(server_pid)
    for b in bots:
        b.close()

    total = stats.accepted + stats.rejected
    return {
        'rooms': n_rooms, 'clients': len(bots), 'setup_seconds': round(setup_s, 1),
        'actions': total, 'accepted': stats.accepted, 'rejected': stats.rejected, 'timeouts': stats.timeouts,
        'games_finished': stats.games, 'throughput_per_s': round(total / elapsed, 1),
        'ack_ms': {'p50': round(pct(stats.ack_ms, 50), 2), 'p95': round(pct(stats.ack_ms, 95), 2),
                   'p99': round(pct(stats.ack_ms, 99), 2), 'max': round(max(stats.ack_ms, default=float('nan')), 2)},
        'broadcast_ms': {'p50': round(pct(stats.bcast_ms, 50), 2), 'p95': round(pct(stats.bcast_ms, 95), 2),
                         'p99': round(pct(stats.bcast_ms, 99), 2)},
        'server_mem_mb': {'before': round(mem_before, 1), 'after': round(mem_after, 1)},
    }


def collision_test(url):
    """300 個人都要求房號 1234：每個人都要分到不同的房間，不能把別人踢掉。"""
    bots = []
    codes = []
    for i in range(300):
        b = Bot(url, f'#col{i}', Stats(), {}, random.Random(i), 0)
        b.connect()
        b.sio.emit('create_room', {'room_code': '1234', 'token': b.token, 'user_info': {'name': 'C'}})
        codes.append(b.wait('room_created')['room_code'])
        bots.append(b)
    for b in bots:
        b.close()
    return {'requests': len(codes), 'distinct_rooms': len(set(codes)), 'got_requested_code': codes.count('1234')}


def ai_benchmark(samples=60):
    """逾時代打的運算時間（同一個程序裡直接呼叫，不經網路）。"""
    from server.engine import game as g
    from server.state import rooms
    rng = random.Random(7)
    g.socketio.emit = lambda *a, **k: None   # 不真的送出
    times = {2: [], 4: []}
    for players in times:
        for _ in range(samples):
            st = g.init_game_state('bench', players, rng.choice([1, 2]))
            rooms['bench'] = {'game_state': st}
            # 先隨機下到移動期的某個時間點
            for _ in range(rng.randint(2 * players, 2 * players + 40)):
                cc = current_color(st)
                opts = legal_next_states(st, cc) if cc else []
                if not opts:
                    break
                st.update(rng.choice(opts))
            if st['phase'] != 'movement':
                continue
            st['selectedPieceIndex'], st['stepsTaken'] = -1, 0
            t0 = time.perf_counter()
            g.force_ai_move('bench')
            times[players].append((time.perf_counter() - t0) * 1000)
    rooms.pop('bench', None)
    return {f'{p}_players': {'samples': len(v), 'mean_ms': round(statistics.mean(v), 2),
                             'p95_ms': round(pct(v, 95), 2), 'max_ms': round(max(v), 2)}
            for p, v in times.items() if v}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rooms', default='10,50,100,200', help='每個等級的房間數，逗號分隔')
    ap.add_argument('--seconds', type=float, default=15, help='每個等級跑幾秒')
    ap.add_argument('--think', type=float, default=0.3, help='機器人每次操作間隔（秒），真人大約 0.5～2')
    ap.add_argument('--port', type=int, default=5055)
    ap.add_argument('--out', default=os.path.join(ROOT, 'tests', 'stress_results.json'))
    args = ap.parse_args()

    url = f'http://127.0.0.1:{args.port}'
    server = subprocess.Popen([sys.executable, '-c', SERVER_CODE.format(root=ROOT, port=args.port)],
                              env={**os.environ, 'SECRET_KEY': SECRET},
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                probe = socketio.Client(); probe.connect(url, transports=['websocket'], wait_timeout=2); probe.disconnect()
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        else:
            raise RuntimeError('後端沒有啟動')

        import platform
        results = {'machine': {'cpu_count': os.cpu_count(), 'processor': platform.processor(),
                               'python': platform.python_version(), 'os': platform.platform()},
                   'think_seconds': args.think, 'seconds_per_level': args.seconds, 'levels': []}
        print(f'後端已啟動（PID {server.pid}），每個等級跑 {args.seconds:g} 秒，機器人操作間隔約 {args.think:g} 秒\n')
        hdr = f'{"房間":>4} {"連線":>5} {"動作數":>7} {"每秒":>6} {"拒絕":>4} {"逾時":>4} ' \
              f'{"ack p50":>8} {"p95":>7} {"p99":>7} {"廣播p50":>8} {"p95":>7} {"記憶體MB":>9}'
        print(hdr)
        rng = random.Random(1)
        for n in [int(x) for x in args.rooms.split(',') if x]:
            r = run_level(url, n, args.seconds, args.think, rng, server.pid)
            results['levels'].append(r)
            print(f'{r["rooms"]:>4} {r["clients"]:>5} {r["actions"]:>7} {r["throughput_per_s"]:>6} '
                  f'{r["rejected"]:>4} {r["timeouts"]:>4} {r["ack_ms"]["p50"]:>8} {r["ack_ms"]["p95"]:>7} '
                  f'{r["ack_ms"]["p99"]:>7} {r["broadcast_ms"]["p50"]:>8} {r["broadcast_ms"]["p95"]:>7} '
                  f'{r["server_mem_mb"]["after"]:>9}', flush=True)

        print('\n房號撞號測試（300 人都要 1234）…', end=' ', flush=True)
        results['collision'] = col = collision_test(url)
        print(f'{col["distinct_rooms"]} 間不同的房間，只有 {col["got_requested_code"]} 人拿到 1234')
        results['server_mem_after_all_mb'] = round(server_memory_mb(server.pid), 1)
    finally:
        server.terminate()
        server.wait(10)

    print('逾時代打運算時間…', end=' ', flush=True)
    results['ai_move'] = ai = ai_benchmark()
    print('  '.join(f'{k}: 平均 {v["mean_ms"]} ms / p95 {v["p95_ms"]} ms / 最慢 {v["max_ms"]} ms' for k, v in ai.items()))

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f'\n結果已存到 {args.out}')
    bad = any(lv['timeouts'] or lv['rejected'] for lv in results['levels']) or \
        results['collision']['distinct_rooms'] != results['collision']['requests']
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
