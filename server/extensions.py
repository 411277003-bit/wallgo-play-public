"""跨模組共用的 Flask 擴充物件。先建立、在 create_app() 裡才綁到 app。"""
from flask_socketio import SocketIO

socketio = SocketIO(cors_allowed_origins="*")
