"""建立 Flask app：掛上 CORS、HTTP API、Socket.IO 事件。"""
from flask import Flask
from flask_cors import CORS

from server.extensions import socketio


def create_app():
    app = Flask(__name__)
    CORS(app)

    from server.routes import auth, history, friends
    app.register_blueprint(auth.bp)
    app.register_blueprint(history.bp)
    app.register_blueprint(friends.bp)

    socketio.init_app(app)
    # 匯入時 @socketio.on 就會把事件註冊上去
    from server.sockets import rooms, game, voice  # noqa: F401
    return app
