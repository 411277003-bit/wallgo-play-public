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

if __name__ == '__main__':
    # 這是本地測試用的設定
    app.run(host='0.0.0.0', port=5000, debug=True)
