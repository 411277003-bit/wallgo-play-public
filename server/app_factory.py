"""建立 Flask app：掛上 CORS、HTTP API、Socket.IO 事件，以及統一的錯誤回應。"""
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from server.extensions import socketio
from server.validation import BadInput


def create_app():
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024   # 單一請求最多 2 MB（覆盤資料最大）
    CORS(app)

    @app.errorhandler(BadInput)
    def bad_input(e):
        return jsonify({"success": False, "message": e.message}), e.status

    @app.errorhandler(HTTPException)
    def http_error(e):
        # 415（不是 JSON）、413（太大）、404 等也回 JSON，前端才讀得到訊息
        return jsonify({"success": False, "message": e.description or e.name}), e.code

    @app.errorhandler(Exception)
    def unexpected_error(e):
        app.logger.exception(e)   # 細節只留在伺服器紀錄，不回給使用者
        return jsonify({"success": False, "message": "伺服器發生錯誤，請稍後再試。"}), 500

    from server.routes import auth, history, friends
    app.register_blueprint(auth.bp)
    app.register_blueprint(history.bp)
    app.register_blueprint(friends.bp)

    socketio.init_app(app)
    # 匯入時 @socketio.on 就會把事件註冊上去
    from server.sockets import rooms, game, voice  # noqa: F401
    return app
