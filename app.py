from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import os

app = Flask(__name__)
CORS(app)

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

# API：玩家註冊
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    user_id = data.get('id')
    username = data.get('username')
    password = data.get('password')

    # 檢查 ID 是否重複
    if users_col.find_one({"id": user_id}):
        return jsonify({"success": False, "message": "此 ID 已被註冊！"})

    # 建立新玩家文件 (Document)
    new_user = {
        "id": user_id,
        "username": username,
        "password": password,
        "avatar": username[0].upper(),
        "is_online": 1
    }
    
    # 寫入 MongoDB
    users_col.insert_one(new_user)
    
    return jsonify({
        "success": True, 
        "message": "註冊成功！",
        "user": {"id": user_id, "name": username, "avatar": username[0].upper()}
    })

# API：玩家登入
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user_id = data.get('id')
    password = data.get('password')

    # 尋找玩家
    user = users_col.find_one({"id": user_id})
    
    if user:
        if user['password'] == password: # 驗證密碼
            # 更新為上線狀態
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

# API：儲存戰績
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

# API：讀取戰績
@app.route('/api/get_history', methods=['POST'])
def get_history():
    data = request.json
    user_id = data.get('user_id')
    # 根據 user_id 尋找該玩家所有戰績，排除 MongoDB 預設的 _id 欄位
    records = list(history_col.find({"user_id": user_id}, {"_id": 0}))
    return jsonify({"success": True, "history": records})

# API：清除戰績
@app.route('/api/clear_history', methods=['POST'])
def clear_history():
    data = request.json
    user_id = data.get('user_id')
    # 刪除該玩家的所有戰績
    history_col.delete_many({"user_id": user_id})
    return jsonify({"success": True})


# ================= 新增：好友系統 API =================

# API：發送好友邀請
@app.route('/api/send_friend_request', methods=['POST'])
def send_friend_request():
    data = request.json
    requester_id = data.get('requester_id')
    receiver_id = data.get('receiver_id')

    if requester_id == receiver_id:
        return jsonify({"success": False, "message": "不能加自己為好友喔！"})

    # 檢查對方是否存在
    receiver = users_col.find_one({"id": receiver_id})
    if not receiver:
        return jsonify({"success": False, "message": "找不到此玩家 ID！請確認輸入正確。"})

    # 檢查是否已經是好友或已送過邀請
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

    # 寫入邀請紀錄
    friends_col.insert_one({
        "requester_id": requester_id,
        "receiver_id": receiver_id,
        "status": "pending" # pending 代表等待審核
    })
    return jsonify({"success": True, "message": "好友邀請已送出！等待對方同意。"})

# API：獲取好友名單與邀請狀態
@app.route('/api/get_friends', methods=['POST'])
def get_friends():
    data = request.json
    user_id = data.get('user_id')

    # 尋找與我有關係的所有紀錄
    relations = friends_col.find({
        "$or": [{"requester_id": user_id}, {"receiver_id": user_id}]
    })

    friends_list = []
    pending_sent = []
    pending_received = []

    for rel in relations:
        # 判斷對方是誰
        other_id = rel['receiver_id'] if rel['requester_id'] == user_id else rel['requester_id']
        other_user = users_col.find_one({"id": other_id})
        
        if not other_user:
            continue
        
        # 整理對方顯示的資料
        user_info = {
            "id": other_user['id'], 
            "name": other_user['username'], 
            "avatar": other_user['avatar']
        }

        if rel['status'] == 'accepted':
            friends_list.append(user_info)
        elif rel['status'] == 'pending':
            if rel['requester_id'] == user_id:
                pending_sent.append(user_info) # 我送出的，等對方同意
            else:
                pending_received.append(user_info) # 別人送我的，等我同意
    
    return jsonify({
        "success": True, 
        "friends": friends_list,
        "pending_sent": pending_sent,
        "pending_received": pending_received
    })

# API：處理(同意/拒絕)好友邀請
@app.route('/api/handle_friend_request', methods=['POST'])
def handle_friend_request():
    data = request.json
    requester_id = data.get('requester_id') # 發送邀請的人
    receiver_id = data.get('receiver_id')   # 點擊同意/拒絕的人 (我自己)
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
