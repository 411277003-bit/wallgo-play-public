"""戰績去重（只影響顯示，資料庫不動）。

- 新紀錄有 game_id：同一個 game_id 只算一次。
- 舊紀錄沒有 game_id：連線對局每位玩家各存一筆、舊版還可能同一人存兩次，
  而且日期是各自電腦的時間，會差幾秒。所以「勝利格數、明細（去掉「(你)」）都一樣，
  時間又相差在 MERGE_WINDOW 秒內」就當成同一局。日期看不懂的紀錄一律保留，不合併。

純 Python，不碰 Flask 也不碰資料庫，tests/test_history_dedupe.py 直接測。
"""
import re
from datetime import datetime

MERGE_WINDOW = 120   # 秒

# 前端用 toLocaleString('zh-TW') 存的日期，例如「2026/11/18 下午9:04:33」；也接受 24 小時制「2026/11/18 21:04:33」
_DATE_RE = re.compile(r'(\d{4})/(\d{1,2})/(\d{1,2})\s*(上午|下午)?\s*(\d{1,2}):(\d{2})(?::(\d{2}))?')


def parse_date(text):
    m = _DATE_RE.search(str(text or ''))
    if not m:
        return None
    y, mo, d, ampm, h, mi, s = m.groups()
    h = int(h)
    if ampm == '下午' and h < 12:
        h += 12
    elif ampm == '上午' and h == 12:
        h = 0
    try:
        return datetime(int(y), int(mo), int(d), h, int(mi), int(s or 0))
    except ValueError:
        return None


def _old_key(record):
    details = (record.get('details') or '').replace('(你)', '')
    return (record.get('winScore'), details)


def dedupe(records, window=MERGE_WINDOW):
    """依原本順序走過 records，同一局只留第一筆。回傳新的 list，不改動傳入的資料。"""
    seen_ids = set()
    kept_times = {}   # 舊紀錄：(格數, 明細) → 已保留那幾筆的時間
    out = []
    for r in records:
        gid = r.get('game_id')
        if gid:
            if gid in seen_ids:
                continue
            seen_ids.add(gid)
            out.append(r)
            continue

        t = parse_date(r.get('date'))
        if t is None:
            out.append(r)
            continue
        key = _old_key(r)
        times = kept_times.setdefault(key, [])
        if any(abs((t - other).total_seconds()) <= window for other in times):
            continue
        times.append(t)
        out.append(r)
    return out
