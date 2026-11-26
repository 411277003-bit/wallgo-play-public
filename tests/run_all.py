"""一次跑完所有測試：python tests/run_all.py   （加 --stress 連壓力測試一起跑，約 2～3 分鐘）

需要：pip install -r requirements.txt、Node.js。不需要 MongoDB。
"""
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

SUITES = [
    ('棋規（前端 JS）', '單元', ['node', 'tests/rules.test.mjs']),
    ('棋規（後端 Python）', '單元', [sys.executable, 'tests/test_rules.py']),
    ('戰績去重', '單元', [sys.executable, 'tests/test_history_dedupe.py']),
    ('棋步驗證', '單元／邊界／防作弊', [sys.executable, 'tests/test_validate.py']),
    ('前後端一致性', '整合', [sys.executable, 'tests/test_client_parity.py']),
    ('HTTP API', '單元／邊界／資安／模糊', [sys.executable, 'tests/test_api.py']),
    ('即時連線（Socket.IO）', '整合／資安', [sys.executable, 'tests/test_server.py']),
    ('好友列表 XSS', '資安', ['node', 'tests/lobby_xss.test.mjs']),
]
if '--stress' in sys.argv:
    SUITES.append(('壓力測試', '壓力', [sys.executable, 'tests/stress_test.py']))

env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONWARNINGS': 'ignore'}
rows, all_ok = [], True
for name, kind, cmd in SUITES:
    print(f'▶ {name} …', end=' ', flush=True)
    t0 = time.perf_counter()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)
    secs = time.perf_counter() - t0
    passed = p.stdout.count('✓')
    failed = p.stdout.count('✗')
    ok = p.returncode == 0
    all_ok &= ok
    print(f'{"通過" if ok else "失敗"}（{secs:.1f} 秒）')
    if not ok:
        print('\n'.join(line for line in (p.stdout + p.stderr).splitlines()
                        if '✗' in line or 'Error' in line or 'Traceback' in line)[-3000:])
    rows.append((name, kind, passed, failed, secs, ok))

print('\n' + '─' * 64)
print(f'{"測試":<22}{"類型":<20}{"通過":>6}{"失敗":>6}{"秒":>8}')
for name, kind, passed, failed, secs, ok in rows:
    width = lambda s, n: s + ' ' * max(0, n - sum(2 if ord(ch) > 0x2e80 else 1 for ch in s))  # noqa: E731
    print(f'{width(name, 22)}{width(kind, 20)}{passed:>6}{failed:>6}{secs:>8.1f}')
total_pass = sum(r[2] for r in rows)
total_fail = sum(r[3] for r in rows)
print('─' * 64)
print(f'合計 {total_pass} 項通過、{total_fail} 項失敗' + ('' if all_ok else '　⚠️ 有測試失敗'))
sys.exit(0 if all_ok else 1)
