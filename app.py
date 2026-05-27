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

if __name__ == '__main__':
    # 這是本地測試用的設定
    app.run(host='0.0.0.0', port=5000, debug=True)