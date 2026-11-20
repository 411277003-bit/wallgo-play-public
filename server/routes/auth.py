"""帳號 API：註冊、登入、重設密碼、修改資料。"""
from flask import Blueprint, request, jsonify

from server.db import users_col

bp = Blueprint(__name__.rsplit('.', 1)[-1], __name__)


@bp.route('/api/register', methods=['POST'])
def register():
    data = request.json
    user_id = data.get('id')
    username = data.get('username')
    password = data.get('password')

    if users_col.find_one({"id": user_id}):
        return jsonify({"success": False, "message": "This ID is already taken."})

    new_user = {
        "id": user_id,
        "username": username,
        "password": password,
        "avatar": username[0].upper(),
        "is_online": 1
    }
    users_col.insert_one(new_user)
    
    return jsonify({
        "success": True, 
        "message": "Sign-up successful!",
        "user": {"id": user_id, "name": username, "avatar": username[0].upper()}
    })

@bp.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user_id = data.get('id')
    password = data.get('password')

    user = users_col.find_one({"id": user_id})
    if user:
        if user['password'] == password: 
            users_col.update_one({"id": user_id}, {"$set": {"is_online": 1}})
            return jsonify({
                "success": True, 
                "message": "Logged in.",
                "user": {"id": user['id'], "name": user['username'], "avatar": user['avatar']}
            })
        else:
            return jsonify({"success": False, "message": "Incorrect password."})
    else:
        return jsonify({"success": False, "message": "Player ID not found."})

@bp.route('/api/reset_password', methods=['POST'])
def reset_password():
    data = request.json
    user_id = data.get('id')
    new_password = data.get('new_password')
    
    user = users_col.find_one({"id": user_id})
    if user:
        users_col.update_one({"id": user_id}, {"$set": {"password": new_password}})
        return jsonify({"success": True, "message": "Password reset! Please log in with your new password."})
    else:
        return jsonify({"success": False, "message": "Player ID not found. Please check and try again."})

@bp.route('/api/update_profile', methods=['POST'])
def update_profile():
    data = request.json
    user_id = data.get('id')
    new_username = data.get('username')
    new_avatar = data.get('avatar')
    
    user = users_col.find_one({"id": user_id})
    if user:
        users_col.update_one(
            {"id": user_id}, 
            {"$set": {"username": new_username, "avatar": new_avatar}}
        )
        return jsonify({"success": True, "message": "個人資料更新成功！"})
    else:
        return jsonify({"success": False, "message": "找不到此玩家 ID！"})
