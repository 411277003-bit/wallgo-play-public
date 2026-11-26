"""帳號 API：註冊、登入、重設密碼、修改資料。

- 密碼用 werkzeug 的 generate_password_hash 雜湊後才存，資料庫看不到原文。
  舊帳號的明文密碼會在下次登入成功時自動換成雜湊。
- 忘記密碼要輸入「救援碼」才能重設（註冊時發給玩家，只顯示一次；資料庫裡同樣只存雜湊）。
  舊帳號沒有救援碼，會在下次登入時補發。
- 登入／重設密碼同一個帳號 10 分鐘內最多錯 5 次。
- 修改資料要帶登入 token，只能改自己的。
"""
import hmac
import secrets

from flask import Blueprint, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from server import db
from server import validation as v
from server.auth_token import issue, current_user_id
from server.ratelimit import login_limiter, reset_limiter

bp = Blueprint(__name__.rsplit('.', 1)[-1], __name__)

HASH_PREFIXES = ('scrypt:', 'pbkdf2:')


def _is_hashed(stored):
    return isinstance(stored, str) and stored.startswith(HASH_PREFIXES)


def _password_matches(stored, given):
    if _is_hashed(stored):
        return check_password_hash(stored, given)
    # 舊帳號：資料庫裡還是明文，用固定時間比較避免時間側錄
    return isinstance(stored, str) and hmac.compare_digest(stored.encode(), given.encode())


def _new_recovery_code():
    """8 碼救援碼，例如 7F3A-91C2（去掉容易看錯的字元）。"""
    alphabet = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'
    raw = ''.join(secrets.choice(alphabet) for _ in range(8))
    return f'{raw[:4]}-{raw[4:]}'


def _normalize_code(code):
    return code.replace('-', '').replace(' ', '').upper()


def _public_user(user):
    return {"id": user['id'], "name": user['username'], "avatar": user['avatar']}


@bp.route('/api/register', methods=['POST'])
def register():
    data = v.json_body()
    user_id = v.player_id(data.get('id'))
    username = v.text(data.get('username'), '暱稱', v.NAME_MAX)
    password = v.password(data.get('password'))

    if db.users_col.find_one({"id": user_id}):
        return jsonify({"success": False, "message": "This ID is already taken."})

    recovery_code = _new_recovery_code()
    new_user = {
        "id": user_id,
        "username": username,
        "password": generate_password_hash(password),
        "recovery": generate_password_hash(_normalize_code(recovery_code)),
        "avatar": username[0].upper(),
        "is_online": 1
    }
    db.users_col.insert_one(new_user)

    return jsonify({
        "success": True,
        "message": "Sign-up successful!",
        "user": _public_user(new_user),
        "token": issue(user_id),
        "recovery_code": recovery_code,
    })


@bp.route('/api/login', methods=['POST'])
def login():
    data = v.json_body()
    user_id = v.player_id(data.get('id'))
    password = v.password(data.get('password'), check_min=False)   # 舊帳號的密碼可能比現在的下限短

    if login_limiter.blocked(user_id):
        raise v.BadInput('密碼錯誤次數過多，請 10 分鐘後再試。', 429)

    user = db.users_col.find_one({"id": user_id})
    if not user:
        return jsonify({"success": False, "message": "Player ID not found."})
    if not _password_matches(user.get('password'), password):
        login_limiter.fail(user_id)
        return jsonify({"success": False, "message": "Incorrect password."})

    login_limiter.reset(user_id)
    updates = {"is_online": 1}
    if not _is_hashed(user.get('password')):
        updates["password"] = generate_password_hash(password)   # 舊帳號：順手把明文換成雜湊
    recovery_code = None
    if not user.get('recovery'):
        recovery_code = _new_recovery_code()                      # 舊帳號：補發救援碼
        updates["recovery"] = generate_password_hash(_normalize_code(recovery_code))
    db.users_col.update_one({"id": user_id}, {"$set": updates})

    result = {"success": True, "message": "Logged in.", "user": _public_user(user), "token": issue(user_id)}
    if recovery_code:
        result["recovery_code"] = recovery_code
    return jsonify(result)


@bp.route('/api/reset_password', methods=['POST'])
def reset_password():
    data = v.json_body()
    user_id = v.player_id(data.get('id'))
    code = v.text(data.get('recovery_code'), '救援碼', 20)
    new_password = v.password(data.get('new_password'), '新密碼')

    if reset_limiter.blocked(user_id):
        raise v.BadInput('救援碼錯誤次數過多，請 10 分鐘後再試。', 429)

    user = db.users_col.find_one({"id": user_id})
    # 帳號不存在、沒有救援碼、救援碼錯誤都回同一句話，不透露是哪一種
    if not user or not user.get('recovery') or not check_password_hash(user['recovery'], _normalize_code(code)):
        reset_limiter.fail(user_id)
        return jsonify({"success": False, "message": "Player ID 或救援碼不正確。"})

    reset_limiter.reset(user_id)
    login_limiter.reset(user_id)
    new_code = _new_recovery_code()   # 救援碼用過就換一組
    db.users_col.update_one({"id": user_id}, {"$set": {
        "password": generate_password_hash(new_password),
        "recovery": generate_password_hash(_normalize_code(new_code)),
    }})
    return jsonify({"success": True, "message": "Password reset! Please log in with your new password.",
                    "recovery_code": new_code})


@bp.route('/api/update_profile', methods=['POST'])
def update_profile():
    user_id = current_user_id()
    data = v.json_body()
    new_username = v.text(data.get('username'), '暱稱', v.NAME_MAX)
    new_avatar = data.get('avatar')
    new_avatar = v.text(new_avatar, '頭像', v.AVATAR_MAX) if new_avatar else new_username[0].upper()

    result = db.users_col.update_one({"id": user_id}, {"$set": {"username": new_username, "avatar": new_avatar}})
    if result.matched_count == 0:
        return jsonify({"success": False, "message": "找不到此玩家 ID！"})
    return jsonify({"success": True, "message": "個人資料更新成功！",
                    "user": {"id": user_id, "name": new_username, "avatar": new_avatar}})
