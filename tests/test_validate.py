"""執行：python tests/test_validate.py   （需要 pip install -r requirements.txt）

伺服器端棋步驗證（server/engine/validate.py）的單元測試：
  1. 指定盤面：輪錯人、方形斜走、拆別人的牆、破牆兩次、疊子…都要被擋
  2. 隨機完整對局：2～4 人 × 規則 1／2，每一步合法操作都必須被接受（不能誤擋正常玩家）
  3. 隨機作弊：在對局中隨機竄改盤面，每一次都必須被擋，而且伺服器狀態完全不變
  4. 壞資料：型別、座標、數量亂填，只能回「拒絕」，不能讓伺服器拋例外
"""
import copy
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from server.engine.game import init_game_state  # noqa: E402
from server.engine.rules import check_game_over  # noqa: E402
from server.engine.validate import (apply_client_action, legal_next_states, current_color,  # noqa: E402
                                    restore_state, Invalid)

failed = 0
total = 0


def check(name, ok, detail=''):
    global failed, total
    total += 1
    print(f'  {"✓" if ok else "✗"} {name}' + (f'   ← {detail}' if not ok and detail else ''))
    failed += 0 if ok else 1


def section(title):
    print(f'\n【{title}】')


def to_client(s):
    """伺服器格式 → 前端送上來的格式（牆是 [["r,c", color]]）。"""
    return {
        'pieces': copy.deepcopy(s['pieces']),
        'walls': [[f"{w['r']},{w['c']}", w['color']] for w in s['walls']],
        'phase': s['phase'], 'turnIndex': s['turnIndex'],
        'selectedPieceIndex': s['selectedPieceIndex'], 'movedPieceIndex': s['movedPieceIndex'],
        'stepsTaken': s['stepsTaken'], 'moveDir': copy.deepcopy(s.get('moveDir')),
        'playersInfo': copy.deepcopy(s['playersInfo']), 'gameId': s.get('gameId'),
        'rules': s.get('rules'), 'activeColors': list(s['activeColors']),
    }


def new_state(players=2, rules=1):
    s = init_game_state('t', players, rules)
    s.pop('timer_job')
    return s


def snapshot(s):
    return copy.deepcopy({k: v for k, v in s.items()})


def try_action(state, data, actor):
    before = snapshot(state)
    ok, reason = apply_client_action(state, data, actor)
    if not ok and snapshot(state) != before:
        raise AssertionError('被拒絕的動作改到了伺服器狀態')
    return ok, reason


def place_all(state, cells):
    """依序放棋，每一步都走驗證。"""
    for r, c in cells:
        cc = current_color(state)
        nxt = next(n for n in legal_next_states(state, cc) if (n['pieces'][-1]['r'], n['pieces'][-1]['c']) == (r, c))
        ok, reason = try_action(state, to_client(nxt), cc)
        assert ok, reason


# ════════════════════════════════════════════════════════════
section('1. 指定盤面')

s = new_state(2, 1)
nxt = legal_next_states(s, 'red')
check('放置期：紅色第一手有 49 個合法位置', len(nxt) == 49)
check('還沒輪到藍色，藍色沒有任何合法動作', legal_next_states(s, 'blue') == [])
ok, reason = try_action(s, to_client(nxt[0]), 'blue')
check('藍色搶著下紅色的棋 → 拒絕', not ok and reason == '還沒輪到你', reason)
ok, _ = try_action(s, to_client(nxt[0]), 'yellow')
check('不在這一局的顏色 → 拒絕', not ok)
ok, _ = try_action(s, to_client(nxt[0]), 'red')
check('紅色下自己的棋 → 接受', ok)
bad = to_client(s)
bad['pieces'].append({'color': 'blue', 'r': 0, 'c': 0})
bad['turnIndex'] = 2
ok, _ = try_action(s, bad, 'blue')
check('疊在已經有棋的格子上 → 拒絕', not ok)
bad = to_client(s)
bad['pieces'] += [{'color': 'blue', 'r': 2, 'c': 2}, {'color': 'blue', 'r': 4, 'c': 4}]
bad['turnIndex'] = 2
ok, _ = try_action(s, bad, 'blue')
check('一次放兩顆 → 拒絕', not ok)
bad = to_client(s)
bad['pieces'].append({'color': 'blue', 'r': 1, 'c': 2})
bad['turnIndex'] = 2
ok, _ = try_action(s, bad, 'blue')
check('放在牆的位置（奇數座標）→ 拒絕', not ok)

# 走子
s = new_state(2, 1)
place_all(s, [(6, 6), (0, 0), (12, 12), (12, 0)])
check('四顆放完進入移動期', s['phase'] == 'movement' and current_color(s) == 'red')
sel = to_client(s); sel['selectedPieceIndex'] = 0
check('選自己的棋 → 接受', try_action(s, sel, 'red')[0])
far = to_client(s); far['pieces'][0].update(r=6, c=10); far['stepsTaken'] = 1; far['moveDir'] = [0, 1]
check('一步跳兩格（瞬移）→ 拒絕', not try_action(s, far, 'red')[0])
diag = to_client(s); diag['pieces'][0].update(r=8, c=8); diag['stepsTaken'] = 1; diag['moveDir'] = [1, 1]
check('斜走 → 拒絕', not try_action(s, diag, 'red')[0])
step = to_client(s); step['pieces'][0].update(r=6, c=8); step['stepsTaken'] = 1; step['moveDir'] = [0, 1]
check('往右走一格 → 接受', try_action(s, step, 'red')[0])
other = to_client(s); other['selectedPieceIndex'] = 2
check('走了一步之後不能換選別顆 → 拒絕', not try_action(s, other, 'red')[0])
turn = to_client(s); turn['pieces'][0].update(r=8, c=8); turn['stepsTaken'] = 0; turn['phase'] = 'wall_building'
turn['movedPieceIndex'] = 0; turn['selectedPieceIndex'] = -1
check('規則 1：第二步可以轉彎 → 接受', try_action(s, turn, 'red')[0])
wall = to_client(s); wall['walls'].append(['1,0', 'red']); wall.update(phase='movement', movedPieceIndex=-1, turnIndex=1)
check('蓋牆在別顆棋旁邊（不是剛走的棋）→ 拒絕', not try_action(s, wall, 'red')[0])
wall = to_client(s); wall['walls'].append(['8,9', 'blue']); wall.update(phase='movement', movedPieceIndex=-1, turnIndex=1)
check('蓋牆但牆的顏色寫成對手的 → 拒絕', not try_action(s, wall, 'red')[0])
wall = to_client(s); wall['walls'].append(['8,9', 'red']); wall.update(phase='movement', movedPieceIndex=-1, turnIndex=0)
check('蓋完牆不換人（連下兩回合）→ 拒絕', not try_action(s, wall, 'red')[0])
wall = to_client(s); wall['walls'].append(['8,9', 'red']); wall.update(phase='movement', movedPieceIndex=-1, turnIndex=1)
check('在剛走的棋旁邊蓋自己的牆並換人 → 接受', try_action(s, wall, 'red')[0])
check('換人後新玩家的時間重設為 90 秒', s['playerTimes']['blue'] == 90)

# 破牆
cheat = to_client(s); cheat['walls'] = []; cheat['playersInfo']['blue']['hasBreaker'] = False
check('規則 1：拆別人蓋的牆 → 拒絕', not try_action(s, cheat, 'blue')[0])
toggle = to_client(s); toggle['phase'] = 'wall_breaking'
check('規則 1：自己沒蓋過牆就不能進破牆模式 → 拒絕', not try_action(s, toggle, 'blue')[0])

s = new_state(2, 1)
place_all(s, [(6, 6), (0, 0), (12, 12), (12, 0)])
s['walls'] = [{'r': 6, 'c': 7, 'color': 'red'}, {'r': 1, 'c': 0, 'color': 'blue'}]
toggle = to_client(s); toggle['phase'] = 'wall_breaking'
check('有自己的牆時可以進破牆模式', try_action(s, toggle, 'red')[0])
brk = to_client(s); brk['walls'] = [['6,7', 'red']]; brk['phase'] = 'movement'; brk['playersInfo']['red']['hasBreaker'] = False
check('破牆模式拆對手的牆 → 拒絕', not try_action(s, brk, 'red')[0])
brk = to_client(s); brk['walls'] = [['1,0', 'blue']]; brk['phase'] = 'movement'
check('拆牆但沒有用掉破牆權 → 拒絕', not try_action(s, brk, 'red')[0])
brk['playersInfo']['red']['hasBreaker'] = False
check('拆自己的牆並用掉破牆權 → 接受', try_action(s, brk, 'red')[0])
s['walls'].append({'r': 6, 'c': 5, 'color': 'red'})
again = to_client(s); again['phase'] = 'wall_breaking'
check('破牆權用掉後不能再進破牆模式 → 拒絕', not try_action(s, again, 'red')[0])
revive = to_client(s); revive['playersInfo']['red']['hasBreaker'] = True
check('偷偷把破牆權改回來 → 拒絕', not try_action(s, revive, 'red')[0])

# 停在四周都沒有牆位的地方（邊界情況：角落兩道牆都已經蓋好）
s = new_state(2, 1)
place_all(s, [(0, 0), (12, 12), (12, 0), (6, 6)])
s['walls'] = [{'r': 0, 'c': 1, 'color': 'blue'}, {'r': 1, 'c': 0, 'color': 'blue'}]
sel = to_client(s); sel['selectedPieceIndex'] = 0
try_action(s, sel, 'red')
stay = to_client(s); stay.update(selectedPieceIndex=-1, movedPieceIndex=0, phase='wall_building')
check('角落的棋被兩道牆圍住，只能原地停下', try_action(s, stay, 'red')[0])
skip_wall = to_client(s); skip_wall.update(phase='movement', movedPieceIndex=-1, turnIndex=1)
check('沒有牆位可蓋時，不蓋牆直接換人 → 接受（以前會卡住 90 秒）', try_action(s, skip_wall, 'red')[0])
s2 = new_state(2, 1)
place_all(s2, [(0, 0), (12, 12), (12, 0), (6, 6)])
s2['selectedPieceIndex'] = 0
try_action(s2, {**to_client(s2), 'selectedPieceIndex': -1, 'movedPieceIndex': 0, 'phase': 'wall_building'}, 'red')
check('還有牆位可蓋時，不能跳過蓋牆', not try_action(s2, {**to_client(s2), 'phase': 'movement', 'movedPieceIndex': -1,
                                                       'turnIndex': 1}, 'red')[0])

# 規則 2
s = new_state(2, 2)
place_all(s, [(6, 6), (0, 0), (0, 12), (12, 12)])
check('規則 2：先放圓再放方', [p.get('shape') for p in s['pieces']] == ['circle', 'circle', 'square', 'square'])
fake = new_state(2, 2)
d = to_client(fake); d['pieces'] = [{'color': 'red', 'r': 0, 'c': 0, 'shape': 'square'}]; d['turnIndex'] = 1
check('規則 2：第一顆就放方形 → 拒絕', not try_action(fake, d, 'red')[0])
s['turnIndex'] = 0
sq = to_client(s); sq['selectedPieceIndex'] = 3   # 放置順序紅藍藍紅：第 4 顆是紅色的方形 (12,12)
try_action(s, sq, 'red')
step = to_client(s); step['pieces'][3].update(r=10, c=12); step['stepsTaken'] = 1; step['moveDir'] = [-1, 0]
check('規則 2：方形往上走一格', try_action(s, step, 'red')[0])
bend = to_client(s); bend['pieces'][3].update(r=10, c=10); bend.update(stepsTaken=0, phase='wall_building', movedPieceIndex=3, selectedPieceIndex=-1)
check('規則 2：方形第二步轉彎 → 拒絕', not try_action(s, bend, 'red')[0])
straight = to_client(s); straight['pieces'][3].update(r=8, c=12); straight.update(stepsTaken=0, phase='wall_building', movedPieceIndex=3, selectedPieceIndex=-1)
check('規則 2：方形第二步直走 → 接受', try_action(s, straight, 'red')[0])

# 重新開始、結束
s = new_state(3, 1)
place_all(s, [(0, 0), (0, 2), (0, 4)])
restart = {'phase': 'placement', 'pieces': [], 'walls': [], 'gameId': 'new-game-1'}
check('對局中任何一位玩家都可以重新開始', try_action(s, restart, 'blue')[0] and s['pieces'] == [] and s['gameId'] == 'new-game-1')
check('重新開始沿用房間的人數', s['activeColors'] == ['red', 'blue', 'yellow'])
check('觀戰者（沒有顏色）不能重新開始', not try_action(s, {**restart, 'gameId': 'x2'}, None)[0])
check('gameId 格式不對就不算重新開始', not try_action(s, {**restart, 'gameId': '<script>'}, 'red')[0])
s['phase'] = 'game_over'
check('遊戲結束後沒有合法的棋步', legal_next_states(s, 'red') == [])

# ════════════════════════════════════════════════════════════
section('2. 隨機完整對局：每一步合法操作都要被接受')

rng = random.Random(2026)
games = actions = 0
rejected_legal = []
t0 = time.perf_counter()
for players in (2, 3, 4):
    for rules in (1, 2):
        for _ in range(25):
            s = new_state(players, rules)
            for _ in range(600):
                cc = current_color(s)
                options = legal_next_states(s, cc)
                if not options:
                    break
                pick = rng.choice(options)
                ok, reason = apply_client_action(s, to_client(pick), cc)
                actions += 1
                if not ok:
                    rejected_legal.append(reason)
                    break
                if s['phase'] != 'placement' and check_game_over(s)['over']:
                    break
            games += 1
elapsed = time.perf_counter() - t0
check(f'{games} 局、{actions} 個合法操作全部被接受', not rejected_legal, str(rejected_legal[:3]))
check(f'驗證速度：平均每步 {elapsed / actions * 1000:.3f} ms（< 5 ms）', elapsed / actions < 0.005)

# ════════════════════════════════════════════════════════════
section('3. 隨機作弊：竄改盤面都要被擋，伺服器狀態不變')


def mutations(s, cc, legal):
    """從一個合法結果出發做各種竄改。"""
    base = to_client(rng.choice(legal))
    out = []
    if base['pieces']:
        m = copy.deepcopy(base); p = rng.choice(m['pieces']); p['r'] = (p['r'] + 4) % 14 // 2 * 2; out.append(('瞬移棋子', m))
        m = copy.deepcopy(base); m['pieces'].pop(); out.append(('偷走一顆棋', m))
        m = copy.deepcopy(base); i = rng.randrange(len(m['pieces'])); m['pieces'][i]['color'] = rng.choice([c for c in s['activeColors'] if c != m['pieces'][i]['color']]); out.append(('把棋子換顏色', m))
    free = [(r, c) for r in range(13) for c in range(13) if (r + c) % 2 == 1
            and [f'{r},{c}', cc] not in base['walls'] and not any(w[0] == f'{r},{c}' for w in base['walls'])]
    m = copy.deepcopy(base); r, c = rng.choice(free); m['walls'].append([f'{r},{c}', cc]); out.append(('多蓋一道牆', m))
    if base['walls']:
        m = copy.deepcopy(base); m['walls'].pop(rng.randrange(len(m['walls']))); out.append(('偷拆一道牆', m))
    m = copy.deepcopy(base); m['turnIndex'] = (m['turnIndex'] + 1) % len(s['movementOrder']); out.append(('跳過回合', m))
    m = copy.deepcopy(base); m['playersInfo'][cc]['hasBreaker'] = not m['playersInfo'][cc]['hasBreaker']; out.append(('改破牆權', m))
    m = copy.deepcopy(base); m['phase'] = rng.choice([p for p in ('placement', 'movement', 'wall_building', 'wall_breaking') if p != base['phase'] and not (base['phase'] == 'movement' and p == 'game_over')]); out.append(('跳階段', m))
    return out


tried = blocked = 0
leaks = []
for players in (2, 3, 4):
    for rules in (1, 2):
        for _ in range(3):
            s = new_state(players, rules)
            for _ in range(200):
                cc = current_color(s)
                legal = legal_next_states(s, cc)
                if not legal:
                    break
                legal_keys = {repr(sorted(to_client(x).items(), key=lambda kv: kv[0])) for x in legal}
                for label, m in mutations(s, cc, legal):
                    if repr(sorted(m.items(), key=lambda kv: kv[0])) in legal_keys:
                        continue   # 竄改後剛好還是合法的結果，不算作弊
                    tried += 1
                    ok, _ = try_action(s, m, cc)
                    if ok:
                        leaks.append(label)
                        break
                    blocked += 1
                if leaks:
                    break
                apply_client_action(s, to_client(rng.choice(legal)), cc)
                if s['phase'] != 'placement' and check_game_over(s)['over']:
                    break
check(f'{tried} 次竄改全部被擋（{blocked} 次）', not leaks, str(leaks[:3]))

# ════════════════════════════════════════════════════════════
section('4. 壞資料：只能拒絕，不能拋例外')

s = new_state(2, 1)
place_all(s, [(0, 0), (2, 2)])
garbage = [
    ('牆壁座標是文字', {'walls': [['abc', 'red']]}),
    ('牆壁座標超出棋盤', {'walls': [['99,1', 'red']]}),
    ('牆壁在棋格上', {'walls': [['2,2', 'red']]}),
    ('牆壁顏色亂填', {'walls': [['1,0', 'purple']]}),
    ('棋子座標 999', {'pieces': [{'color': 'red', 'r': 999, 'c': -5}]}),
    ('500 顆棋子', {'pieces': [{'color': 'red', 'r': 0, 'c': 0}] * 500}),
    ('棋子不是物件', {'pieces': [1, 2, 3]}),
    ('棋子座標是小數', {'pieces': [{'color': 'red', 'r': 0.5, 'c': 0}]}),
    ('棋子座標是布林', {'pieces': [{'color': 'red', 'r': True, 'c': 0}]}),
    ('形狀亂填', {'pieces': [{'color': 'red', 'r': 0, 'c': 0, 'shape': 'star'}]}),
    ('phase 亂填', {'phase': 'win'}),
    ('turnIndex 是負數', {'turnIndex': -1}),
    ('turnIndex 超大', {'turnIndex': 10 ** 9}),
    ('moveDir 亂填', {'moveDir': [5, 5], 'stepsTaken': 1}),
    ('playersInfo 是字串', {'playersInfo': 'x'}),
    ('pieces 是 null', {'pieces': None}),
    ('walls 是物件', {'walls': {'a': 1}}),
    ('牆壁 300 道', {'walls': [[f'{r},{c}', 'red'] for r in range(13) for c in range(13) if (r + c) % 2] * 2}),
]
crashes = []
for label, patch in garbage:
    data = {**to_client(s), **patch}
    try:
        ok, _ = try_action(s, data, current_color(s))
        check(f'{label} → 拒絕', not ok)
    except Exception as e:  # noqa: BLE001
        crashes.append(f'{label}: {type(e).__name__} {e}')
check('上面都沒有拋例外', not crashes, '; '.join(crashes))

restored = restore_state({**to_client(s), 'activeColors': ['red', 'blue']}, new_state(2, 1))
check('伺服器重啟後可以用合法盤面重建', restored['pieces'] == s['pieces'])
for label, patch in [('顏色不是從紅色開始', {'activeColors': ['blue', 'red']}),
                     ('5 個顏色', {'activeColors': ['red', 'blue', 'yellow', 'green', 'pink']}),
                     ('同色 3 顆棋', {'pieces': [{'color': 'red', 'r': 0, 'c': c} for c in (0, 2, 4)]}),
                     ('建牆階段卻沒有剛走的棋', {'phase': 'wall_building', 'movedPieceIndex': -1})]:
    try:
        restore_state({**to_client(s), **patch}, new_state(2, 1))
        check(f'重建時擋掉：{label}', False)
    except Invalid:
        check(f'重建時擋掉：{label}', True)

print(f'\n共 {total} 項，{failed} 個失敗' if failed else f'\n全部 {total} 項通過')
sys.exit(1 if failed else 0)
