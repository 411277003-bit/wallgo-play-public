"""好友 API：送出邀請、列表、接受／拒絕。

都要帶登入 token：送邀請的人、審核邀請的人都以 token 裡的 ID 為準，
不能冒用別人的身分送邀請，也不能替別人同意邀請。
"""
from flask import Blueprint, jsonify

from server import db
from server import validation as v
from server.auth_token import current_user_id

bp = Blueprint(__name__.rsplit('.', 1)[-1], __name__)


@bp.route('/api/send_friend_request', methods=['POST'])
def send_friend_request():
    requester_id = current_user_id()
    data = v.json_body()
    receiver_id = v.player_id(data.get('receiver_id'))

    if requester_id == receiver_id:
        return jsonify({"success": False, "message": "不能加自己為好友喔！"})

    receiver = db.users_col.find_one({"id": receiver_id})
    if not receiver:
        return jsonify({"success": False, "message": "Player ID not found. Please check and try again."})

    existing = db.friends_col.find_one({
        "$or": [
            {"requester_id": requester_id, "receiver_id": receiver_id},
            {"requester_id": receiver_id, "receiver_id": requester_id}
        ]
    })

    if existing:
        if existing['status'] == 'accepted':
            return jsonify({"success": False, "message": "你們已經是好友了！"})
        else:
            return jsonify({"success": False, "message": "邀請已存在！請至好友列表查看狀態。"})

    db.friends_col.insert_one({
        "requester_id": requester_id,
        "receiver_id": receiver_id,
        "status": "pending"
    })
    return jsonify({"success": True, "message": "好友邀請已送出！等待對方同意。"})


@bp.route('/api/get_friends', methods=['POST'])
def get_friends():
    user_id = current_user_id()

    relations = db.friends_col.find({
        "$or": [{"requester_id": user_id}, {"receiver_id": user_id}]
    })

    friends_list, pending_sent, pending_received = [], [], []

    for rel in relations:
        other_id = rel['receiver_id'] if rel['requester_id'] == user_id else rel['requester_id']
        other_user = db.users_col.find_one({"id": other_id})
        if not other_user:
            continue

        user_info = {
            "id": other_user['id'],
            "name": other_user['username'],
            "avatar": other_user['avatar']
        }

        if rel['status'] == 'accepted':
            friends_list.append(user_info)
        elif rel['status'] == 'pending':
            if rel['requester_id'] == user_id:
                pending_sent.append(user_info)
            else:
                pending_received.append(user_info)

    return jsonify({
        "success": True,
        "friends": friends_list,
        "pending_sent": pending_sent,
        "pending_received": pending_received
    })


@bp.route('/api/handle_friend_request', methods=['POST'])
def handle_friend_request():
    receiver_id = current_user_id()   # 只有收到邀請的人能審核
    data = v.json_body()
    requester_id = v.player_id(data.get('requester_id'))
    action = data.get('action')
    if action not in ('accept', 'reject'):
        return jsonify({"success": False, "message": "無效的操作"})

    query = {"requester_id": requester_id, "receiver_id": receiver_id, "status": "pending"}
    if action == 'accept':
        result = db.friends_col.update_one(query, {"$set": {"status": "accepted"}})
        found = result.matched_count
    else:
        found = db.friends_col.delete_one(query).deleted_count
    if not found:
        return jsonify({"success": False, "message": "找不到這則好友邀請。"})
    return jsonify({"success": True, "message": "已同意好友請求！" if action == 'accept' else "已拒絕該請求！"})
