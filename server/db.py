"""MongoDB 連線與資料表。connect=False：第一次查詢時才真的連線。"""
import os
from pymongo import MongoClient

MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')

try:
    client = MongoClient(MONGO_URI, connect=False)
    db = client['wallgo_db']
    users_col = db['users']
    history_col = db['history']
    friends_col = db['friends']
    print("✅ 成功連線至 MongoDB 資料庫！")
except Exception as e:
    print(f"❌ MongoDB 連線失敗: {e}")
