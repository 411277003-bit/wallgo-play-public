"""輸入檢查：HTTP API 與 Socket.IO 事件共用。

API 遇到不合格的輸入就丟 BadInput，app_factory 會把它轉成
{"success": false, "message": ...} 加上對應的 HTTP 狀態碼（400／401／429），
不會再因為缺欄位、型別錯誤而變成 500 伺服器錯誤。
"""
import re
import unicodedata

from flask import request

ID_RE = re.compile(r'^#[A-Za-z0-9]{1,16}$')        # 玩家 ID：# 開頭，後面只能英數字
ROOM_RE = re.compile(r'^\d{4}$')                    # 房號：4 位數字
GAME_ID_RE = re.compile(r'^[A-Za-z0-9-]{1,64}$')    # 一局的編號（uuid）

NAME_MAX = 20
AVATAR_MAX = 4          # 一個字母或 emoji（有些 emoji 由多個字元組成）
PASSWORD_MIN = 4
PASSWORD_MAX = 64
CHAT_MAX = 300


class BadInput(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def json_body():
    """取得 JSON 物件；不是 JSON、或不是物件（例如陣列、字串）就回 400。"""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise BadInput('請求格式錯誤：需要 JSON 物件。')
    return data


def _has_control_chars(s):
    return any(unicodedata.category(ch) in ('Cc', 'Cf') and ch not in '‍️' for ch in s)


def player_id(value, field='Player ID'):
    if not isinstance(value, str) or not ID_RE.match(value.strip()):
        raise BadInput(f'{field} 格式錯誤：需以 # 開頭，後面 1～16 個英文或數字（例如 #1234）。')
    return value.strip()


def text(value, field, max_len, min_len=1):
    """一般文字欄位：去頭尾空白、限制長度、不允許控制字元。"""
    if not isinstance(value, str):
        raise BadInput(f'{field} 必須是文字。')
    value = value.strip()
    if len(value) < min_len:
        raise BadInput(f'{field} 不能是空的。' if min_len == 1 else f'{field} 至少要 {min_len} 個字。')
    if len(value) > max_len:
        raise BadInput(f'{field} 最多 {max_len} 個字。')
    if _has_control_chars(value):
        raise BadInput(f'{field} 含有不允許的字元。')
    return value


def password(value, field='密碼', check_min=True):
    """密碼不去空白（空白也是密碼的一部分），只檢查型別與長度。"""
    if not isinstance(value, str) or not value:
        raise BadInput(f'{field} 不能是空的。')
    if check_min and len(value) < PASSWORD_MIN:
        raise BadInput(f'{field} 至少要 {PASSWORD_MIN} 個字。')
    if len(value) > PASSWORD_MAX:
        raise BadInput(f'{field} 最多 {PASSWORD_MAX} 個字。')
    return value


def clean_name(value, fallback, max_len=NAME_MAX):
    """Socket 事件用：名稱不合格時不丟錯，直接截斷或換成預設值（聊天、觀戰名單用）。"""
    if not isinstance(value, str):
        return fallback
    value = ''.join(ch for ch in value.strip() if not _has_control_chars(ch))
    return value[:max_len] or fallback


def room_code(value):
    """合格回傳房號字串，不合格回傳 None（Socket 事件用，不丟錯）。"""
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if isinstance(value, str) and ROOM_RE.match(value):
        return value
    return None


def game_id(value):
    return value if isinstance(value, str) and GAME_ID_RE.match(value) else None
