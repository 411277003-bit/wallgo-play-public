"""伺服器端驗證每一步棋（純函式，不碰網路也不碰 Flask）。

前端每點一下（選棋、走一步、蓋牆、破牆、切換破牆模式…）就把整盤狀態送上來。
以前伺服器照單全收，改一下封包就能憑空多一顆棋、把對手的牆拆掉、或跳過別人的回合。

現在的做法：用 rules.py 列出「目前輪到的玩家這一下所有合法的結果」，
前端送來的盤面必須剛好等於其中一個，否則整個動作被拒絕，伺服器把正確的盤面回給那個人。
這跟 js/game/flow.js 的 handleCellClick／handleWallClick／toggleWallBreaker／endTurn 一一對應。

對外的函式：
    apply_client_action(state, data, actor) → (True, None) 或 (False, 原因)
    restore_state(data)                     → 伺服器重啟後用玩家送來的盤面重建（只做格式與合理性檢查）
"""
import copy

from server.engine.rules import (allColors, boardSize, get_valid_walls, moves_for_piece,
                                 next_shape, breakable_walls)
from server.validation import game_id as valid_game_id

TURN_TIME_LIMIT = 90
PHASES = ('placement', 'movement', 'wall_building', 'wall_breaking', 'game_over')
SHAPES = (None, 'circle', 'square')


class Invalid(Exception):
    pass


# ───────────── 讀取前端送來的資料（格式不對就丟 Invalid） ─────────────

def _int(value, lo, hi, field):
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise Invalid(f'{field} 不合法')
    return value


def parse_pieces(raw, colors):
    if not isinstance(raw, list) or len(raw) > 2 * len(colors):
        raise Invalid('棋子資料不合法')
    pieces, seen = [], set()
    for p in raw:
        if not isinstance(p, dict) or p.get('color') not in colors:
            raise Invalid('棋子資料不合法')
        r, c = _int(p.get('r'), 0, boardSize - 1, '棋子座標'), _int(p.get('c'), 0, boardSize - 1, '棋子座標')
        if r % 2 or c % 2 or (r, c) in seen:
            raise Invalid('棋子座標不合法')
        seen.add((r, c))
        shape = p.get('shape')
        if shape not in SHAPES:
            raise Invalid('棋子形狀不合法')
        piece = {'color': p['color'], 'r': r, 'c': c}
        if shape:
            piece['shape'] = shape
        pieces.append(piece)
    return pieces


def parse_walls(raw, colors):
    """前端送 [["r,c", color], ...]；伺服器內部用 [{r, c, color}, ...]。"""
    if not isinstance(raw, list) or len(raw) > 200:
        raise Invalid('牆壁資料不合法')
    walls, seen = [], set()
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 2 or not isinstance(item[0], str) \
                or item[1] not in colors:
            raise Invalid('牆壁資料不合法')
        parts = item[0].split(',')
        if len(parts) != 2 or not all(x.strip().lstrip('-').isdigit() for x in parts):
            raise Invalid('牆壁座標不合法')
        r, c = int(parts[0]), int(parts[1])
        # 牆只能在「一奇一偶」的位置
        if not (0 <= r < boardSize and 0 <= c < boardSize) or (r + c) % 2 == 0 or (r, c) in seen:
            raise Invalid('牆壁座標不合法')
        seen.add((r, c))
        walls.append({'r': r, 'c': c, 'color': item[1]})
    return walls


def _move_dir(raw):
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise Invalid('moveDir 不合法')
    return [_int(raw[0], -1, 1, 'moveDir'), _int(raw[1], -1, 1, 'moveDir')]


def parse_core(data, state):
    """把前端送來的資料整理成跟 core_key 比對用的形狀。"""
    colors = state['activeColors']
    phase = data.get('phase')
    if phase not in PHASES:
        raise Invalid('phase 不合法')
    n_pieces = 2 * len(colors)
    info = data.get('playersInfo')
    if not isinstance(info, dict):
        raise Invalid('playersInfo 不合法')
    return {
        'pieces': parse_pieces(data.get('pieces'), colors),
        'walls': parse_walls(data.get('walls'), colors),
        'phase': phase,
        'turnIndex': _int(data.get('turnIndex'), 0, len(state['placementQueue']), 'turnIndex'),
        'selectedPieceIndex': _int(data.get('selectedPieceIndex'), -1, n_pieces, 'selectedPieceIndex'),
        'movedPieceIndex': _int(data.get('movedPieceIndex'), -1, n_pieces, 'movedPieceIndex'),
        'stepsTaken': _int(data.get('stepsTaken'), 0, 2, 'stepsTaken'),
        'moveDir': _move_dir(data.get('moveDir')),
        'playersInfo': {c: {'hasBreaker': bool((info.get(c) or {}).get('hasBreaker'))} for c in colors},
    }


def core_key(s):
    """比對兩個狀態是否「同一個結果」時看的欄位。
    - 前端在建牆／破牆後自己判定遊戲結束會送 game_over，伺服器之後自己再判一次，所以當作 movement 比
    - moveDir 只有走到一半（stepsTaken > 0）才有意義"""
    phase = 'movement' if s['phase'] == 'game_over' else s['phase']
    return (
        tuple((p['color'], p['r'], p['c'], p.get('shape')) for p in s['pieces']),
        frozenset((w['r'], w['c'], w['color']) for w in s['walls']),
        phase, s['turnIndex'], s['selectedPieceIndex'], s['movedPieceIndex'], s['stepsTaken'],
        tuple(s['moveDir']) if s['stepsTaken'] > 0 and s.get('moveDir') else None,
        tuple(sorted((c, bool(i.get('hasBreaker'))) for c, i in s['playersInfo'].items())),
    )


# ───────────── 列出所有合法的下一步 ─────────────

CORE_FIELDS = ('pieces', 'walls', 'phase', 'turnIndex', 'selectedPieceIndex', 'movedPieceIndex',
               'stepsTaken', 'moveDir', 'playersInfo')


def current_color(state):
    if state['phase'] == 'game_over':
        return None
    order = state['placementQueue'] if state['phase'] == 'placement' else state['movementOrder']
    return order[state['turnIndex']] if 0 <= state['turnIndex'] < len(order) else None


def _clone(state):
    return {k: copy.deepcopy(state.get(k)) for k in CORE_FIELDS} | {
        k: state[k] for k in ('rules', 'activeColors', 'placementQueue', 'movementOrder')}


def _sign(x):
    return (x > 0) - (x < 0)


def _end_turn(s):
    s.update(movedPieceIndex=-1, selectedPieceIndex=-1, stepsTaken=0, phase='movement',
             turnIndex=(s['turnIndex'] + 1) % len(s['movementOrder']))


def legal_next_states(state, actor):
    """輪到 actor 時，他點一下之後所有可能的盤面（對應 flow.js 的每一種操作）。"""
    cc = current_color(state)
    if cc is None or actor != cc:
        return []
    out = []
    phase = state['phase']
    pieces = state['pieces']

    if phase == 'placement':
        occupied = {(p['r'], p['c']) for p in pieces}
        shape = next_shape(state, cc)
        for r in range(0, boardSize, 2):
            for c in range(0, boardSize, 2):
                if (r, c) in occupied:
                    continue
                s = _clone(state)
                s['pieces'].append({'color': cc, 'r': r, 'c': c, **({'shape': shape} if shape else {})})
                s['turnIndex'] += 1
                if s['turnIndex'] >= len(s['placementQueue']):
                    s['phase'], s['turnIndex'] = 'movement', 0
                out.append(s)

    elif phase == 'movement':
        sel, steps = state['selectedPieceIndex'], state['stepsTaken']
        own = [i for i, p in enumerate(pieces) if p['color'] == cc]
        if sel == -1:
            for i in own:                                   # 選一顆自己的棋
                s = _clone(state)
                s['selectedPieceIndex'], s['stepsTaken'] = i, 0
                out.append(s)
        elif 0 <= sel < len(pieces):
            if steps == 0:
                for i in own:                               # 還沒走之前換選另一顆
                    if i != sel:
                        s = _clone(state)
                        s['selectedPieceIndex'] = i
                        out.append(s)
                s = _clone(state)                            # 點到不能走的地方 = 取消選取
                s['selectedPieceIndex'] = -1
                out.append(s)
            p = pieces[sel]
            for m in moves_for_piece(state, p):
                s = _clone(state)
                if (m['r'], m['c']) == (p['r'], p['c']):     # 點自己 = 停在這裡，開始蓋牆
                    s.update(movedPieceIndex=sel, selectedPieceIndex=-1, stepsTaken=0, phase='wall_building')
                else:
                    if steps == 0:
                        s['moveDir'] = [_sign(m['r'] - p['r']), _sign(m['c'] - p['c'])]
                    s['pieces'][sel] = {**p, 'r': m['r'], 'c': m['c']}
                    s['stepsTaken'] = steps + 1
                    if s['stepsTaken'] >= 2:
                        s.update(movedPieceIndex=sel, selectedPieceIndex=-1, stepsTaken=0, phase='wall_building')
                out.append(s)
        # 進入破牆模式：還沒開始走、破牆權還在、而且有牆可以拆
        if steps == 0 and state['playersInfo'].get(cc, {}).get('hasBreaker') and breakable_walls(state, cc):
            s = _clone(state)
            s['phase'], s['selectedPieceIndex'] = 'wall_breaking', -1
            out.append(s)

    elif phase == 'wall_building':
        moved = state['movedPieceIndex']
        if 0 <= moved < len(pieces):
            mp = pieces[moved]
            walls = get_valid_walls(state['walls'], mp['r'], mp['c'])
            for w in walls:
                s = _clone(state)
                s['walls'].append({'r': w['r'], 'c': w['c'], 'color': cc})
                _end_turn(s)
                out.append(s)
            if not walls:                                    # 四周沒有牆位可蓋：不蓋牆直接換人
                s = _clone(state)
                _end_turn(s)
                out.append(s)

    elif phase == 'wall_breaking':
        s = _clone(state)                                    # 再按一次破牆鈕 = 取消
        s['phase'] = 'movement'
        out.append(s)
        if state['playersInfo'].get(cc, {}).get('hasBreaker'):
            for w in breakable_walls(state, cc):
                s = _clone(state)
                s['walls'] = [x for x in s['walls'] if (x['r'], x['c']) != (w['r'], w['c'])]
                s['playersInfo'][cc]['hasBreaker'] = False
                s['phase'] = 'movement'
                out.append(s)
    return out


# ───────────── 套用前端送來的動作 ─────────────

def _fresh_state(state, new_game_id):
    """重新開始：沿用房間的顏色與規則，其他全部歸零。"""
    colors = state['activeColors']
    state.update({
        'phase': 'placement', 'turnIndex': 0, 'pieces': [], 'walls': [], 'territories': [],
        'selectedPieceIndex': -1, 'movedPieceIndex': -1, 'stepsTaken': 0, 'moveDir': None,
        'playersInfo': {c: {'hasBreaker': True} for c in colors},
        'playerTimes': {c: TURN_TIME_LIMIT for c in colors},
        'gameId': new_game_id,
    })


def is_restart(data, state):
    gid = data.get('gameId')
    return (data.get('phase') == 'placement' and data.get('pieces') == [] and data.get('walls') in ([], None)
            and valid_game_id(gid) is not None and gid != state.get('gameId'))


def apply_client_action(state, data, actor):
    """驗證並套用一個動作。成功時直接改 state（伺服器權威狀態），失敗時 state 完全不動。"""
    if actor not in state['activeColors']:
        return False, '你不是這一局的玩家'

    if is_restart(data, state):
        _fresh_state(state, data['gameId'])
        return True, None

    try:
        claimed = parse_core(data, state)
    except Invalid as e:
        return False, f'資料格式錯誤：{e}'

    if current_color(state) != actor:
        return False, '還沒輪到你'
    want = core_key(claimed)
    for nxt in legal_next_states(state, actor):
        if core_key(nxt) == want:
            before = (state['phase'] == 'placement', state['turnIndex'])
            for k in CORE_FIELDS:
                state[k] = nxt[k]
            # 換人時，新的玩家重新有 90 秒（跟 flow.js 的 resetCurrentPlayerTimer 一致）
            if (state['phase'] == 'placement', state['turnIndex']) != before:
                nc = current_color(state)
                if nc:
                    state['playerTimes'][nc] = TURN_TIME_LIMIT
            return True, None
    return False, '不合法的操作'


def restore_state(data, base):
    """伺服器重啟、房間資料不見時，用玩家送來的盤面重建。
    這時伺服器沒有「上一步」可以比對，只能檢查格式與基本合理性（顏色、座標、數量、順序）。
    base 是 init_game_state 建出來的空白狀態。回傳重建好的 state，不合理就丟 Invalid。"""
    colors = data.get('activeColors')
    if colors is None:
        n = len(data.get('playersInfo') or {}) or 2
        colors = allColors[:max(2, min(4, n))]
    if not isinstance(colors, list) or colors != allColors[:len(colors)] or not 2 <= len(colors) <= 4:
        raise Invalid('activeColors 不合法')
    base.update(activeColors=colors, placementQueue=colors + colors[::-1], movementOrder=list(colors),
                playersInfo={c: {'hasBreaker': True} for c in colors},
                playerTimes={c: TURN_TIME_LIMIT for c in colors})
    if data.get('rules') in (1, 2):
        base['rules'] = data['rules']

    core = parse_core(data, base)
    count = {}
    for p in core['pieces']:
        count[p['color']] = count.get(p['color'], 0) + 1
    if any(n > 2 for n in count.values()):
        raise Invalid('棋子數量不合法')
    order = base['placementQueue'] if core['phase'] == 'placement' else base['movementOrder']
    if core['turnIndex'] >= len(order):
        raise Invalid('turnIndex 不合法')
    for k in ('selectedPieceIndex', 'movedPieceIndex'):
        if core[k] >= len(core['pieces']):
            raise Invalid(f'{k} 不合法')
    if core['phase'] == 'wall_building' and core['movedPieceIndex'] < 0:
        raise Invalid('movedPieceIndex 不合法')
    base.update(core)

    times = data.get('playerTimes')
    if isinstance(times, dict):
        for c in colors:
            t = times.get(c)
            if isinstance(t, int) and not isinstance(t, bool):
                base['playerTimes'][c] = max(0, min(TURN_TIME_LIMIT, t))
    gid = valid_game_id(data.get('gameId'))
    if gid:
        base['gameId'] = gid
    return base
