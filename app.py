from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, join_room, leave_room, emit
from pymongo import MongoClient
import os

app = Flask(__name__)
CORS(app)

# 初始化 SocketIO，允許跨域連線
socketio = SocketIO(app, cors_allowed_origins="*")

# 🔐 從環境變數讀取 MongoDB 連線字串，本地測試時若沒有環境變數則自動用本地端
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')

try:
    client = MongoClient(MONGO_URI)
    db = client['wallgo_db']       # 資料庫名稱
    users_col = db['users']        # 玩家集合 (Collection)
    history_col = db['history']    # 戰績資料表
    friends_col = db['friends']    # 好友關係與邀請資料表
    print("✅ 成功連線至 MongoDB 資料庫！")
except Exception as e:
    print(f"❌ MongoDB 連線失敗: {e}")

# ================= 記憶體資料區 =================
# 暫存目前的房間資訊
rooms = {}

# ================= 帳號 API =================
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    user_id = data.get('id')
    username = data.get('username')
    password = data.get('password')

    if users_col.find_one({"id": user_id}):
        return jsonify({"success": False, "message": "此 ID 已被註冊！"})

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
        "message": "註冊成功！",
        "user": {"id": user_id, "name": username, "avatar": username[0].upper()}
    })

@app.route('/api/login', methods=['POST'])
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
                "message": "登入成功",
                "user": {"id": user['id'], "name": user['username'], "avatar": user['avatar']}
            })
        else:
            return jsonify({"success": False, "message": "密碼錯誤"})
    else:
        return jsonify({"success": False, "message": "找不到此玩家 ID"})

# ================= 戰績 API =================
@app.route('/api/save_history', methods=['POST'])
def save_history():
    data = request.json
    history_col.insert_one({
        "user_id": data.get('user_id'),
        "date": data.get('date'),
        "winner": data.get('winner'),
        "winScore": data.get('winScore'),
        "details": data.get('details')
    })
    return jsonify({"success": True, "message": "戰績儲存成功"})

@app.route('/api/get_history', methods=['POST'])
def get_history():
    data = request.json
    user_id = data.get('user_id')
    records = list(history_col.find({"user_id": user_id}, {"_id": 0}))
    return jsonify({"success": True, "history": records})

@app.route('/api/clear_history', methods=['POST'])
def clear_history():
    data = request.json
    user_id = data.get('user_id')
    history_col.delete_many({"user_id": user_id})
    return jsonify({"success": True})

# ================= 好友系統 API =================
@app.route('/api/send_friend_request', methods=['POST'])
def send_friend_request():
    data = request.json
    requester_id = data.get('requester_id')
    receiver_id = data.get('receiver_id')

    if requester_id == receiver_id:
        return jsonify({"success": False, "message": "不能加自己為好友喔！"})

    receiver = users_col.find_one({"id": receiver_id})
    if not receiver:
        return jsonify({"success": False, "message": "找不到此玩家 ID！請確認輸入正確。"})

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

@app.route('/api/get_friends', methods=['POST'])
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

@app.route('/api/handle_friend_request', methods=['POST'])
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

# ================= 即時連線 (WebSocket) 房間系統 =================
@socketio.on('create_room')
def handle_create_room(data):
    room_code = data.get('room_code')
    user_info = data.get('user_info')
    
    join_room(room_code)
    rooms[room_code] = {'players': [user_info], 'status': 'waiting'}
    
    emit('room_created', {'room_code': room_code, 'players': rooms[room_code]['players']})

@socketio.on('join_room')
def handle_join_room(data):
    room_code = data.get('room_code')
    user_info = data.get('user_info')
    
    if room_code in rooms:
        if len(rooms[room_code]['players']) >= 4:
            emit('join_error', {'message': '房間已滿！不能再加入了。'})
        else:
            if not any(p['id'] == user_info['id'] for p in rooms[room_code]['players']):
                join_room(room_code)
                rooms[room_code]['players'].append(user_info)
            
            emit('room_updated', {'room_code': room_code, 'players': rooms[room_code]['players']}, to=room_code)
    else:
        emit('join_error', {'message': '找不到此房間！請確認代碼是否正確。'})

@socketio.on('leave_room')
def handle_leave_room(data):
    room_code = data.get('room_code')
    user_id = data.get('user_id')
    if room_code in rooms:
        leave_room(room_code)
        rooms[room_code]['players'] = [p for p in rooms[room_code]['players'] if p['id'] != user_id]
        if len(rooms[room_code]['players']) == 0:
            del rooms[room_code]
        else:
            emit('room_updated', {'room_code': room_code, 'players': rooms[room_code]['players']}, to=room_code)

@socketio.on('start_game')
def handle_start_game(data):
    room_code = data.get('room_code')
    # 告訴房間內的所有人：遊戲開始了！準備切換畫面
    emit('game_started', {'room_code': room_code}, to=room_code)

@socketio.on('game_action')
def handle_game_action(data):
    room_code = data.get('room_code')
    # 當某個玩家下棋、移動或蓋牆時，將這個動作廣播給房間內的「其他人」
    emit('update_board', data, to=room_code, include_self=False)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
