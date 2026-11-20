"""伺服器記憶體裡的即時資料（重啟就會清空，前端會在重連時補回對局狀態）。"""

# 房號 → {'players': [...], 'status': 'waiting'|'playing', 'rules': 1|2, 'game_state': {...}}
rooms = {}

# sid → (room_code, 顯示名稱, 是否觀戰)，斷線時用來通知房內其他人
sid_info = {}
