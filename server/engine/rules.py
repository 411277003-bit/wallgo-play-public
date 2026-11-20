"""Wall Go 棋規（Python 版）。純函式，不碰網路也不碰 Flask。

前端的 js/shared/rules.js 是同一套規則；兩邊都要通過 tests/rule_cases.json，
跑 python tests/test_rules.py 檢查這一份。

state 欄位：pieces [{color, r, c, shape?}]、walls [{r, c, color}]、rules 1|2、
stepsTaken、moveDir [dr, dc]、activeColors、playersInfo。
"""

boardSize = 13
allColors = ['red', 'blue', 'yellow', 'green']
DIRS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def get_piece_index(pieces, r, c):
    for i, p in enumerate(pieces):
        if p['r'] == r and p['c'] == c:
            return i
    return -1

def has_wall_between(walls, r1, c1, r2, c2):
    if r1 == r2 and c1 == c2: return False
    wallR = (r1 + r2) / 2
    wallC = (c1 + c2) / 2
    for w in walls:
        if w['r'] == wallR and w['c'] == wallC:
            return True
    return False

def get_valid_moves(pieces, walls, startR, startC):
    valid_moves = []
    for r in range(0, boardSize, 2):
        for c in range(0, boardSize, 2):
            dr = abs(startR - r)
            dc = abs(startC - c)
            if (dr == 2 and dc == 0) or (dr == 0 and dc == 2) or (dr == 0 and dc == 0):
                if get_piece_index(pieces, r, c) == -1 or (r == startR and c == startC):
                    if not has_wall_between(walls, startR, startC, r, c):
                        valid_moves.append({'r': r, 'c': c})
    return valid_moves

def next_shape(state, color):
    """規則 2：每人先放圓形、再放方形；規則 1 沒有形狀。"""
    if state.get('rules') != 2:
        return None
    has_circle = any(p['color'] == color and p.get('shape') == 'circle' for p in state['pieces'])
    return 'square' if has_circle else 'circle'

def breakable_walls(state, color):
    """可以拆的牆。規則 1：自己蓋的牆；規則 2：自己棋子四周的牆（不論誰蓋的）。"""
    if state.get('rules') != 2:
        return [w for w in state['walls'] if w['color'] == color]
    around = set()
    for p in state['pieces']:
        if p['color'] == color:
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                around.add((p['r'] + dr, p['c'] + dc))
    return [w for w in state['walls'] if (w['r'], w['c']) in around]

def get_valid_walls(walls, pR, pC):
    valid_walls = []
    dirs = [[-1, 0], [1, 0], [0, -1], [0, 1]]
    for dr, dc in dirs:
        wr, wc = pR + dr, pC + dc
        if 0 <= wr < boardSize and 0 <= wc < boardSize:
            is_empty = True
            for w in walls:
                if w['r'] == wr and w['c'] == wc:
                    is_empty = False
                    break
            if is_empty:
                valid_walls.append({'r': wr, 'c': wc})
    return valid_walls

def evaluate_board(pieces, walls, aiColor):
    score = 0
    aiMobility = 0
    oppMobility = 0
    for p in pieces:
        moves_count = len(get_valid_moves(pieces, walls, p['r'], p['c']))
        if p['color'] == aiColor:
            aiMobility += moves_count
            score -= (abs(p['r'] - 6) + abs(p['c'] - 6)) * 0.5
        else:
            oppMobility += moves_count
    
    score += (aiMobility * 2.5) - oppMobility
    if aiMobility == 0: score -= 10000
    return score


def moves_for_piece(state, piece):
    """選中的棋子這一步能去哪：規則 2 方形棋第二步只能沿第一步方向（或停在原地）。"""
    moves = get_valid_moves(state['pieces'], state['walls'], piece['r'], piece['c'])
    if state.get('rules') != 2 or piece.get('shape') != 'square' or state.get('stepsTaken') != 1 or not state.get('moveDir'):
        return moves
    dr, dc = state['moveDir']
    return [m for m in moves
            if (m['r'] == piece['r'] and m['c'] == piece['c'])
            or (m['r'] == piece['r'] + 2 * dr and m['c'] == piece['c'] + 2 * dc)]


def score_board(state):
    """把盤面切成被牆隔開的區域；只有一種顏色的區域算那個顏色的領地。
    回傳 (scores, territories{"r,c": color}, has_mixed_territory)"""
    wall_set = {(w['r'], w['c']) for w in state['walls']}
    piece_at = {(p['r'], p['c']): p['color'] for p in state['pieces']}
    scores = {c: 0 for c in state['activeColors']}
    territories = {}
    visited = set()
    has_mixed = False

    for r in range(0, boardSize, 2):
        for c in range(0, boardSize, 2):
            if (r, c) in visited:
                continue
            queue = [(r, c)]
            visited.add((r, c))
            region, colors = [], set()
            while queue:
                cr, cc = queue.pop(0)
                region.append((cr, cc))
                if (cr, cc) in piece_at:
                    colors.add(piece_at[(cr, cc)])
                for dr, dc in DIRS:
                    nr, nc = cr + dr * 2, cc + dc * 2
                    if 0 <= nr < boardSize and 0 <= nc < boardSize \
                            and (cr + dr, cc + dc) not in wall_set and (nr, nc) not in visited:
                        visited.add((nr, nc))
                        queue.append((nr, nc))
            if len(colors) > 1:
                has_mixed = True
            elif len(colors) == 1:
                color = next(iter(colors))
                if color in scores:
                    scores[color] += len(region)
                for cell in region:
                    territories[f"{cell[0]},{cell[1]}"] = color
    return scores, territories, has_mixed


def any_player_can_move(state):
    """是否還有任何玩家能合法行動（能破牆，或有棋子走完還能蓋牆）。"""
    for color in state['activeColors']:
        info = state['playersInfo'].get(color, {})
        if info.get('hasBreaker') and breakable_walls(state, color):
            return True
        for p in state['pieces']:
            if p['color'] != color:
                continue
            for m in get_valid_moves(state['pieces'], state['walls'], p['r'], p['c']):
                if get_valid_walls(state['walls'], m['r'], m['c']):
                    return True
    return False


def check_game_over(state):
    """回傳 {'over', 'reason': 'sealed'|'stalemate'|None, 'scores', 'territories'}。"""
    scores, territories, has_mixed = score_board(state)
    if not has_mixed:
        return {'over': True, 'reason': 'sealed', 'scores': scores, 'territories': territories}
    if not any_player_can_move(state):
        return {'over': True, 'reason': 'stalemate', 'scores': scores, 'territories': territories}
    return {'over': False, 'reason': None, 'scores': scores, 'territories': territories}
