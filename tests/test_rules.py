"""執行：python tests/test_rules.py
用 tests/rule_cases.json 的盤面檢查伺服器的 Python 棋規（server/engine/rules.py）。
跟 node tests/rules.test.mjs 跑的是同一批案例，兩邊都過代表前後端棋規一致。不需要安裝任何套件。"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from server.engine import rules  # noqa: E402

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def keys(items):
    return sorted(i if isinstance(i, str) else f"{i['r']},{i['c']}" for i in items)


with open(os.path.join(ROOT, 'tests', 'rule_cases.json'), encoding='utf-8') as f:
    cases = json.load(f)['cases']

failed = 0
for tc in cases:
    state = {
        'rules': tc['rules'],
        'pieces': tc['pieces'],
        'walls': [{'r': int(k.split(',')[0]), 'c': int(k.split(',')[1]), 'color': v} for k, v in tc['walls']],
        'stepsTaken': tc.get('stepsTaken', 0),
        'moveDir': tc.get('moveDir'),
    }
    want = tc['expect']
    check = tc['check']
    if check == 'movesForPiece':
        got, want = keys(rules.moves_for_piece(state, state['pieces'][tc['piece']])), sorted(want)
    elif check == 'validWalls':
        got, want = keys(rules.get_valid_walls(state['walls'], *tc['at'])), sorted(want)
    elif check == 'breakableWalls':
        got, want = keys(rules.breakable_walls(state, tc['color'])), sorted(want)
    elif check == 'nextShape':
        got = rules.next_shape(state, tc['color'])
    elif check == 'checkGameOver':
        state['activeColors'] = tc['colors']
        state['playersInfo'] = {c: {'hasBreaker': True} for c in tc['colors']}
        r = rules.check_game_over(state)
        got = {'over': r['over']}
        if 'reason' in want:
            got['reason'] = r['reason']
        if 'scores' in want:
            got['scores'] = r['scores']
    else:
        raise ValueError(f'未知的 check：{check}')

    if got == want:
        print(f'  ✓ {tc["name"]}')
    else:
        failed += 1
        print(f'  ✗ {tc["name"]}\n      預期 {want}\n      實際 {got}')

print(f'\n{failed} 個失敗' if failed else f'\n全部 {len(cases)} 個通過')
sys.exit(1 if failed else 0)
