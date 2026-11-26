"""跨模組共用的 Flask 擴充物件。先建立、在 create_app() 裡才綁到 app。"""
from flask_socketio import SocketIO

# 明確指定 gevent：電腦上同時裝了 eventlet 時，Flask-SocketIO 會自動優先選 eventlet，
# 結果 gevent.spawn 的倒數計時協程永遠不會執行（沒有 sync_time、逾時也不會代打）
socketio = SocketIO(cors_allowed_origins="*", async_mode='gevent')
