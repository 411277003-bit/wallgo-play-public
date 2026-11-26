"""伺服器記憶體裡的即時資料（重啟就會清空，前端會在重連時補回對局狀態）。"""

# 房號 → {'players': [...], 'status': 'waiting'|'playing', 'rules': 1|2, 'game_state': {...},
#         'restored': True（伺服器重啟後由玩家補回的房間）, 'seats': {color: user_id}（補回的房間用）}
rooms = {}

# 對局頁的連線：sid → {'room', 'name', 'spectator', 'color', 'uid'}
# 用來判斷「這個連線是哪個顏色的玩家」、斷線時通知房內其他人、算觀戰名單
sid_info = {}

# 大廳等待室的連線：sid → (room_code, user_id)。建房／入房的人直接關網頁時，用來把他移出等待室
lobby_sids = {}
