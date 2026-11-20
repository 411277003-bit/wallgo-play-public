"""好友 API：送出邀請、列表、接受／拒絕。"""
from flask import Blueprint, request, jsonify

from server.db import users_col, friends_col

bp = Blueprint(__name__.rsplit('.', 1)[-1], __name__)


@bp.route('/api/send_friend_request', methods=['POST'])
def send_friend_request():
    data = request.json
    requester_id = data.get('requester_id')
    receiver_id = data.get('receiver_id')

    if requester_id == receiver_id:
        return jsonify({"success": False, "message": "不能加自己為好友喔！"})

    receiver = users_col.find_one({"id": receiver_id})
    if not receiver:
        return jsonify({"success": False, "message": "Player ID not found. Please check and try again."})

    existing = friends_col.find_one({
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

    friends_col.insert_one({
        "requester_id": requester_id,
        "receiver_id": receiver_id,
        "status": "pending" 
    })
    return jsonify({"success": True, "message": "好友邀請已送出！等待對方同意。"})

@bp.route('/api/get_friends', methods=['POST'])
def get_friends():
    data = request.json
    user_id = data.get('user_id')

    relations = friends_col.find({
        "$or": [{"requester_id": user_id}, {"receiver_id": user_id}]
    })

    friends_list, pending_sent, pending_received = [], [], []

    for rel in relations:
        other_id = rel['receiver_id'] if rel['requester_id'] == user_id else rel['requester_id']
        other_user = users_col.find_one({"id": other_id})
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
    data = request.json
    requester_id = data.get('requester_id') 
    receiver_id = data.get('receiver_id')   
    action = data.get('action')

    if action == 'accept':
        friends_col.update_one(
            {"requester_id": requester_id, "receiver_id": receiver_id},
            {"$set": {"status": "accepted"}}
        )
        return jsonify({"success": True, "message": "已同意好友請求！"})
    elif action == 'reject':
        friends_col.delete_one({"requester_id": requester_id, "receiver_id": receiver_id})
        return jsonify({"success": True, "message": "已拒絕該請求！"})
    
    return jsonify({"success": False, "message": "無效的操作"})
