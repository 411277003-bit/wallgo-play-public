"""戰績 API：儲存、讀取、全站統計、清除。"""
from flask import Blueprint, request, jsonify

from server.db import history_col

bp = Blueprint(__name__.rsplit('.', 1)[-1], __name__)


@bp.route('/api/save_history', methods=['POST'])
def save_history():
    data = request.json
    history_col.insert_one({
        "user_id": data.get('user_id'),
        "date": data.get('date'),
        "winner": data.get('winner'),
        "winScore": data.get('winScore'),
        "details": data.get('details'),
        "replayData": data.get('replayData', "")
    })
    return jsonify({"success": True, "message": "戰績儲存成功"})

@bp.route('/api/get_history', methods=['POST'])
def get_history():
    data = request.json
    user_id = data.get('user_id')
    records = list(history_col.find({"user_id": user_id}, {"_id": 0}))
    return jsonify({"success": True, "history": records})

@bp.route('/api/global_stats', methods=['GET'])
def global_stats():
    """全站統整數據：所有玩家的對局數、參與人數、圍地紀錄與最新戰報。
    連線對局每位參與者都會各存一筆，所以用（日期、勝利格數、去掉「(你)」的明細）去重，
    才不會把同一局算成好幾場。"""
    records = list(history_col.find({}, {"replayData": 0}).sort("_id", -1))
    games, latest = {}, []
    for r in records:
        details = (r.get("details") or "").replace("(你)", "")
        key = (r.get("date"), r.get("winScore"), details)
        if key in games:
            continue
        games[key] = r
        if len(latest) < 5:
            latest.append({
                "date": r.get("date"),
                "winner": (r.get("winner") or "").replace("(你)", ""),
                "winScore": r.get("winScore"),
            })
    scores = [g.get("winScore") for g in games.values() if isinstance(g.get("winScore"), (int, float))]
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
    data = request.json
    user_id = data.get('user_id')
    history_col.delete_many({"user_id": user_id})
    return jsonify({"success": True})
