"""語音（WebRTC）信令轉送：伺服器只負責把雙方的連線資訊轉交，聲音不經過伺服器。

只轉送給「同一個房間」裡的人：沒進房間的連線不能送，也不能指定別的房間的人當收件者。
"""
from flask import request
from flask_socketio import emit

from server.extensions import socketio
from server.state import sid_info

SIGNAL_TYPES = {'hello', 'listen', 'talk-start', 'talk-stop', 'offer', 'answer', 'ice', 'bye'}


@socketio.on('voice_signal')
def handle_voice_signal(data):
    """WebRTC 語音的信令轉送：有 to 就單送給那個人，沒有就廣播給房內其他人。"""
    data = data if isinstance(data, dict) else {}
    me = sid_info.get(request.sid)
    if not me or data.get('type') not in SIGNAL_TYPES:
        return
    room_code = me['room']
    payload = {'from': request.sid, 'type': data['type'], 'data': data.get('data')}
    target = data.get('to')
    if target:
        other = sid_info.get(target) if isinstance(target, str) else None
        if other and other['room'] == room_code:
            emit('voice_signal', payload, to=target)
    else:
        emit('voice_signal', payload, to=room_code, include_self=False)
