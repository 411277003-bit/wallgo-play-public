"""執行：python tests/test_history_dedupe.py   （不需要安裝任何套件）
檢查戰績顯示時的去重：同一局合併、不同局不能被誤合併。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from server.history_dedupe import dedupe, parse_date  # noqa: E402

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

failed = 0


def check(name, ok):
    global failed
    print(f'  {"✓" if ok else "✗"} {name}')
    failed += 0 if ok else 1


def rec(date, score=26, details='紅(你):26 | 藍:18', gid=None, user='a'):
    r = {'user_id': user, 'date': date, 'winScore': score, 'details': details, 'winner': 'kuokuo'}
    if gid:
        r['game_id'] = gid
    return r


check('看得懂下午時間', parse_date('2026/11/18 下午9:04:33').hour == 21)
check('上午 12 點是半夜 0 點', parse_date('2026/11/18 上午12:05:00').hour == 0)
check('下午 12 點是中午 12 點', parse_date('2026/11/18 下午12:05:00').hour == 12)
check('看得懂 24 小時制', parse_date('2026/11/18 21:04:33').hour == 21)
check('亂碼日期回傳 None', parse_date('不是日期') is None)

check('舊紀錄：差幾秒、內容一樣 → 合併成一筆',
      len(dedupe([rec('2026/11/18 下午9:04:33'), rec('2026/11/18 下午9:04:35')])) == 1)
check('舊紀錄：兩位玩家各存一筆（只差在誰有「(你)」）→ 合併',
      len(dedupe([rec('2026/11/18 下午9:04:33', details='紅(你):26 | 藍:18'),
                  rec('2026/11/18 下午9:04:40', details='紅:26 | 藍(你):18', user='b')])) == 1)
check('舊紀錄：相差超過 2 分鐘 → 當成兩局，不合併',
      len(dedupe([rec('2026/11/18 下午9:04:33'), rec('2026/11/18 下午9:10:00')])) == 2)
check('舊紀錄：時間很近但格數不同 → 不合併',
      len(dedupe([rec('2026/11/18 下午9:04:33', score=26), rec('2026/11/18 下午9:04:35', score=25)])) == 2)
check('舊紀錄：日期看不懂 → 保留，不合併',
      len(dedupe([rec('???'), rec('???')])) == 2)
check('新紀錄：同一個 game_id → 只留一筆',
      len(dedupe([rec('2026/11/20 下午9:00:00', gid='g1'), rec('2026/11/20 下午9:00:05', gid='g1', user='b')])) == 1)
check('新紀錄：不同 game_id 就算內容、時間一樣也不合併',
      len(dedupe([rec('2026/11/20 下午9:00:00', gid='g1'), rec('2026/11/20 下午9:00:00', gid='g2')])) == 2)
records = [rec('2026/11/18 下午9:04:33'), rec('2026/11/18 下午9:04:35'), rec('2026/11/18 下午8:00:00', score=25)]
result = dedupe(records)
check('保留原本順序、留下第一筆', result == [records[0], records[2]])
check('不會改動傳入的資料', len(records) == 3)

print(f'\n{failed} 個失敗' if failed else '\n全部通過')
sys.exit(1 if failed else 0)
