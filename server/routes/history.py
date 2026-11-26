"""戰績 API：儲存、讀取、全站統計、清除。

除了全站統計之外都要帶登入 token，玩家 ID 以 token 為準（不能讀、存、清別人的戰績）。
"""
from flask import Blueprint, jsonify

from server import db
from server import validation as v
from server.auth_token import current_user_id
from server.history_dedupe import dedupe

bp = Blueprint(__name__.rsplit('.', 1)[-1], __name__)

MAX_SCORE = 49            # 7×7 棋格
REPLAY_MAX = 1_500_000    # 覆盤資料最多約 1.5 MB（一般一局遠小於這個）


@bp.route('/api/save_history', methods=['POST'])
def save_history():
    user_id = current_user_id()
    data = v.json_body()
    win_score = data.get('winScore')
    if isinstance(win_score, bool) or not isinstance(win_score, int) or not 0 <= win_score <= MAX_SCORE:
        raise v.BadInput(f'winScore 必須是 0～{MAX_SCORE} 的整數。')
    replay = data.get('replayData', "")
    if not isinstance(replay, str) or len(replay) > REPLAY_MAX:
        raise v.BadInput('覆盤資料格式錯誤或太大。')
    details = data.get('details') or ''
    record = {
        "user_id": user_id,
        "date": v.text(data.get('date'), 'date', 40),
        "winner": v.text(data.get('winner'), 'winner', 120),
        "winScore": win_score,
        "details": v.text(details, 'details', 300, min_len=0) if details else '',
        "replayData": replay,
    }
    game_id = data.get('game_id')
    if game_id is not None and not v.game_id(game_id):
        raise v.BadInput('game_id 格式錯誤。')
    if game_id:
        # 同一個玩家的同一局只存一次：重新整理、斷線重連後前端再送一次也不會多一筆
        # 篩選條件裡的 user_id、game_id 在新增時會自動寫入，$setOnInsert 只放其他欄位
        fields = {k: val for k, val in record.items() if k != "user_id"}
        db.history_col.update_one({"user_id": user_id, "game_id": game_id},
                                  {"$setOnInsert": fields}, upsert=True)
    else:
        db.history_col.insert_one(record)   # 舊版前端沒有 game_id
    return jsonify({"success": True, "message": "戰績儲存成功"})


@bp.route('/api/get_history', methods=['POST'])
def get_history():
    user_id = current_user_id()
    # 顯示時合併同一局的重複紀錄（資料庫不動），規則見 server/history_dedupe.py
    records = dedupe(list(db.history_col.find({"user_id": user_id}, {"_id": 0})))
    return jsonify({"success": True, "history": records})


@bp.route('/api/global_stats', methods=['GET'])
def global_stats():
    """全站統整數據：所有玩家的對局數、參與人數、圍地紀錄與最新戰報。
    連線對局每位參與者都會各存一筆，同一局只算一次（server/history_dedupe.py）。"""
    records = list(db.history_col.find({}, {"replayData": 0}).sort("_id", -1))
    games = dedupe(records)   # 同一局只算一次，規則見 server/history_dedupe.py
    latest = [{
        "date": r.get("date"),
        "winner": (r.get("winner") or "").replace("(你)", ""),
        "winScore": r.get("winScore"),
    } for r in games[:5]]
    scores = [g.get("winScore") for g in games if isinstance(g.get("winScore"), (int, float))]
    return jsonify({
        "success": True,
        "totalGames": len(games),
        "players": len({r.get("user_id") for r in records if r.get("user_id")}),
        "bestScore": max(scores) if scores else 0,
        "avgScore": round(sum(scores) / len(scores), 1) if scores else 0,
        "latest": latest,
    })


@bp.route('/api/clear_history', methods=['POST'])
def clear_history():
    user_id = current_user_id()
    db.history_col.delete_many({"user_id": user_id})
    return jsonify({"success": True})
