"""語音（WebRTC）信令轉送：伺服器只負責把雙方的連線資訊轉交，聲音不經過伺服器。"""
from flask import request
from flask_socketio import emit

from server.extensions import socketio


@socketio.on('voice_signal')
def handle_voice_signal(data):
    """WebRTC 語音的信令轉送：有 to 就單送給那個人，沒有就廣播給房內其他人。"""
    room_code = data.get('room_code')
    payload = {'from': request.sid, 'type': data.get('type'), 'data': data.get('data')}
    target = data.get('to')
    if target:
        emit('voice_signal', payload, to=target)
    elif room_code:
        emit('voice_signal', payload, to=room_code, include_self=False)
