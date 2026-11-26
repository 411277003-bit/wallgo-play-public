"""Wall Go 後端進入點。

gevent 的 monkey patch 一定要在其他任何 import 之前執行，所以這個檔只負責啟動；
程式本體都在 server/ 底下：
  server/routes/    帳號、戰績、好友 HTTP API
  server/sockets/   房間、對局同步、語音信令（Socket.IO）
  server/engine/    棋規（rules.py）與對局狀態、逾時代打、計時（game.py）

部署用的 gunicorn 一樣指向 app:app，不用改設定。
"""
import gevent.monkey
gevent.monkey.patch_all()

import sys  # noqa: E402
# Windows 中文環境的主控台是 cp950，印 emoji（✅ ❌ ⚠️）會讓伺服器在啟動時直接當掉
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8', errors='replace')

from server.app_factory import create_app  # noqa: E402
from server.extensions import socketio      # noqa: E402

app = create_app()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
