"""登入憑證：登入／註冊成功時發一張簽章過的 token，之後的 API 與連線都靠它確認「你是誰」。

以前前端直接把 user_id 放在請求裡，任何人改掉 user_id 就能清別人的戰績、改別人的資料；
現在一律以 token 裡的 ID 為準，前端送來的 user_id 不再被採信。

token 用 Flask 內建的 itsdangerous 簽章，伺服器不用存任何東西；
簽章金鑰來自環境變數 SECRET_KEY，部署時一定要設定，否則每次重啟所有人都要重新登入。
"""
import os
import secrets

from flask import request
from itsdangerous import URLSafeTimedSerializer, BadSignature

from server.validation import BadInput, ID_RE

SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    print('⚠️  沒有設定 SECRET_KEY 環境變數，改用隨機金鑰：伺服器重啟後所有人都要重新登入。')

TOKEN_MAX_AGE = 30 * 24 * 3600   # 30 天
_serializer = URLSafeTimedSerializer(SECRET_KEY, salt='wallgo-login')


def issue(user_id):
    return _serializer.dumps({'id': user_id})


def verify(token):
    """合法回傳玩家 ID，否則 None（過期、被竄改、格式錯都算）。"""
    if not isinstance(token, str) or not token or len(token) > 512:
        return None
    try:
        data = _serializer.loads(token, max_age=TOKEN_MAX_AGE)
    except BadSignature:   # SignatureExpired 也是 BadSignature 的子類別
        return None
    uid = data.get('id') if isinstance(data, dict) else None
    return uid if isinstance(uid, str) and ID_RE.match(uid) else None


def current_user_id():
    """HTTP API 用：從 Authorization: Bearer <token> 取出玩家 ID，沒有或無效就回 401。"""
    header = request.headers.get('Authorization', '')
    token = header[7:] if header.startswith('Bearer ') else None
    uid = verify(token)
    if not uid:
        raise BadInput('登入已失效，請重新登入。', 401)
    return uid
