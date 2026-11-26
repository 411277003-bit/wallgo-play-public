"""執行：python tests/test_client_parity.py   （需要 Node.js）

前後端一致性測試：用 Node 跑「真正的」前端對局程式（tests/client_sim.mjs）隨機亂點，
把前端每一次送出的 game_action 交給伺服器的驗證（server/engine/validate.py）。
前端合法送出的每一個動作，伺服器都必須接受 —— 否則正常玩家會被誤判成作弊。
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from server.engine.game import init_game_state, check_end_game  # noqa: E402
from server.engine.validate import apply_client_action  # noqa: E402
from server.state import rooms  # noqa: E402

failed = 0
total = 0


def check(name, ok, detail=''):
    global failed, total
    total += 1
    print(f'  {"✓" if ok else "✗"} {name}' + (f'\n      {detail}' if not ok and detail else ''))
    failed += 0 if ok else 1


print('【前端實際送出的每一步，伺服器都要接受】')
for players in (2, 3, 4):
    for rules in (1, 2):
        lines = subprocess.run(['node', os.path.join(ROOT, 'tests', 'client_sim.mjs'), str(players * 10 + rules), '6',
                                str(players), str(rules)], capture_output=True, text=True, encoding='utf-8', check=True).stdout
        actions = [json.loads(line) for line in lines.splitlines() if line.strip()]
        state = init_game_state('sim', players, rules)
        state.pop('timer_job')
        rooms['sim'] = {'game_state': state}
        problems, finished = [], 0
        for i, a in enumerate(actions):
            ok, reason = apply_client_action(state, a['data'], a['actor'])
            if not ok:
                problems.append(f'第 {i} 步（{a["actor"]}，前端 phase={a["data"]["phase"]}，伺服器 phase={state["phase"]}）：{reason}')
                break
            check_end_game('sim')
            finished += state['phase'] == 'game_over'
        check(f'{players} 人、規則 {rules}：{len(actions)} 個前端動作全部接受（{finished} 局下到結束）',
              not problems and len(actions) > 50, '; '.join(problems[:3]))

print(f'\n共 {total} 項，{failed} 個失敗' if failed else f'\n全部 {total} 項通過')
sys.exit(1 if failed else 0)
