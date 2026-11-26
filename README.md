# Wall Go 牆壁戰棋

線上／單機的牆壁戰棋（Wall Go），支援 2～4 人連線對戰、兩種規則版本、AI 對手、觀戰、聊天室與 WebRTC 語音。

## 遊戲規則版本

開局時可選（單機在「單機對戰」、線上由建立房間的人選），一樣 2～4 人：

| | 牆壁圍棋 1 | 牆壁圍棋 2 |
|---|---|---|
| 棋子 | 每人 2 顆 | 每人 1 圓 1 方（先放圓、再放方） |
| 移動 | 1～2 步，可轉彎 | 圓形同左；方形只能上下左右直走 1～2 步 |
| 破牆（每人一次） | 只能破自己蓋的牆 | 只能破自己棋子四周的牆（誰蓋的都可以） |
| 結束與計分 | 各陣營被牆完全隔開、或沒人能動時結束，數純色領地格數 | 同左 |

線上房間開局後，其他人可在大廳輸入房號按「觀戰」：能看棋、聊天、聽語音，不能下棋。

## 專案架構

```
.
├── index.html              # 大廳畫面（登入、房間、好友、戰績、覆盤）
├── game.html               # 對局畫面（Vue 3，CDN 載入免建置）
├── app.py                  # 後端進入點：只做 gevent patch 並建立 app（部署指向 app:app）
├── requirements.txt
│
├── css/
│   ├── lobby.css           # 大廳樣式
│   └── game.css            # 對局樣式
│
├── js/
│   ├── config.js           # ★ 前端共用設定：後端網址、每回合秒數、語音 STUN/TURN
│   ├── shared/
│   │   └── rules.js        # ★ 棋規（規則 1/2、移動、建牆、破牆、計分、結束判定）
│   ├── lobby/              # 大廳（一般 <script>，共用全域，載入順序寫在 index.html）
│   │   ├── settings.js         # 背景音樂、開場音效
│   │   ├── intro-board.js      # 背景棋盤動畫、開場動畫、跳過開場
│   │   ├── core.js             # 提示、對話框、登入狀態、socket、左側選單、esc()
│   │   ├── rooms.js            # 單機開局、規則版本、線上房間、觀戰
│   │   ├── auth.js             # 登入、註冊、忘記密碼、編輯資料、登出
│   │   ├── history.js          # 戰績、全站統計、覆盤播放器
│   │   ├── friends.js          # 好友
│   │   └── main.js             # 頁面載好後的啟動
│   └── game/               # 對局（ES module，從 main.js 開始載入）
│       ├── main.js             # 按鈕事件、Vue 組裝、棋盤避開上方 HUD、啟動
│       ├── state.js            # 網址參數、登入資訊、畫面狀態 S、小工具
│       ├── flow.js             # 開局、計時、點棋盤、建牆／破牆、換手、結算
│       ├── ai.js               # 單機電腦 AI、逾時代打
│       ├── online.js           # 連線、斷線重連、狀態同步、觀戰名單
│       ├── chat.js             # 聊天室、系統訊息、@標記
│       ├── voice.js            # 語音（原生 WebRTC，信令走 Socket.IO）
│       └── netlog.js           # 封包紀錄器（網址加 &netlog=1 或按 Ctrl+Shift+L）
│
├── server/                 # 後端（Flask + Socket.IO）
│   ├── app_factory.py      # create_app()：掛 CORS、API、Socket.IO 事件
│   ├── extensions.py       # 共用的 socketio 物件
│   ├── db.py               # MongoDB 連線（環境變數 MONGO_URI）
│   ├── state.py            # 記憶體裡的房間與連線資料
│   ├── validation.py       # 輸入檢查（ID、暱稱、密碼、房號的格式與長度）
│   ├── auth_token.py       # 登入 token（簽章金鑰：環境變數 SECRET_KEY）
│   ├── ratelimit.py        # 登入／重設密碼的失敗次數限制
│   ├── history_dedupe.py   # 戰績顯示去重：game_id，或舊紀錄的格數＋明細＋2 分鐘內
│   ├── routes/             # HTTP API：auth（帳號）、history（戰績）、friends（好友）
│   ├── sockets/            # 即時事件：rooms（房間、觀戰）、game（入房、同步、聊天）、voice（語音信令）
│   └── engine/
│       ├── rules.py        # ★ Python 版棋規（跟 js/shared/rules.js 同一套）
│       ├── validate.py     # ★ 伺服器驗證每一步棋（前端送來的盤面必須是合法的下一步）
│       └── game.py         # 對局狀態、逾時代打、結束判定、倒數計時
│
├── tests/
│   ├── rule_cases.json     # ★ JS 與 Python 共用的棋規測試盤面
│   ├── rules.test.mjs      # 測 js/shared/rules.js
│   ├── test_rules.py       # 測 server/engine/rules.py
│   ├── test_server.py      # 模擬玩家與觀戰者，測房間、同步、語音信令、重啟補回、擋作弊、清空房
│   ├── test_history_dedupe.py  # 戰績顯示去重（同一局只算一次）
│   ├── test_validate.py    # 棋步驗證：指定盤面、隨機完整對局、隨機作弊、壞資料
│   ├── test_client_parity.py  # 用 Node 跑真正的前端亂點，確認伺服器不會誤擋（搭配 client_sim.mjs）
│   ├── test_api.py         # HTTP API：正常流程、邊界值、資安、模糊測試（搭配 fake_mongo.py）
│   ├── lobby_xss.test.mjs  # 好友列表 XSS 回歸測試
│   ├── stress_test.py      # 壓力測試：開真的後端，機器人同時開 10～200 間房下棋
│   ├── packet_report.py    # 封包測試：大小、延遲、計時穩定度、斷線重連、作弊封包、實際網路
│   └── run_all.py          # 一次跑完上面全部
│
├── assets/                 # 背景音樂、音效
└── ai-training/            # 獨立的 AlphaZero 訓練專案（目前未被前端引用）
    ├── ai_agent.js         # 網路結構、MCTS 與推論
    ├── wallgo_logic.js     # 純邏輯版棋規，供自我對弈使用
    ├── train.js            # 自我對弈訓練主程式
    ├── worker.js           # 平行自我對局的子進程
    ├── model_io.js         # 模型讀寫
    ├── verify_fixes.mjs    # 17 項回歸測試
    ├── eval_vs_random.mjs  # 對隨機對手的健全性檢查
    ├── diag_visits.mjs     # 根節點訪問分佈診斷
    ├── sync_to_usb.sh      # 把訓練產物同步回隨身碟
    ├── FINDINGS.md         # 訓練診斷紀錄（含尚未解決的問題）
    ├── train.log           # 完整訓練輸出
    ├── alpha_model/        # 最新模型（第 10 輪）
    ├── alpha_model_best/   # 目前最強模型
    ├── alpha_model_ckpt5/  # 第 5 輪 checkpoint
    ├── alpha_model_ckpt10/ # 第 10 輪 checkpoint
    └── archive/            # 舊的（1 步移動 bug）模型，僅供對照
```

前端是純靜態頁面（可放 GitHub Pages），後端另外部署；後端網址改 `js/config.js` 的 `API_URL`，兩個頁面都會跟著用。

**出問題先看哪裡**

| 症狀 | 檔案 |
|---|---|
| 棋走錯、判定錯、計分錯 | `js/shared/rules.js`＋`server/engine/rules.py`，改完跑測試 |
| 對手的棋沒同步、斷線後卡住 | `js/game/online.js`、`server/sockets/game.py` |
| 語音不通 | `js/game/voice.js`、`server/sockets/voice.py` |
| 房間、觀戰 | `js/lobby/rooms.js`、`server/sockets/rooms.py` |
| 版面、顏色、字體 | `css/` |

## 本機執行

**前端**

必須用 HTTP(S) 開啟，不能直接雙擊檔案（JS 模組與麥克風在 `file://` 下都會被瀏覽器擋掉）：

```bash
python -m http.server 5500
# 然後開 http://localhost:5500/index.html
# 單機直接開局：http://localhost:5500/game.html?players=2&rules=2
```

或使用 VS Code 的 Live Server。

**後端**

```bash
pip install -r requirements.txt
export MONGO_URI="mongodb://localhost:27017/"   # 未設定時預設連本機
export SECRET_KEY="一串夠長的隨機字串"           # 登入 token 的簽章金鑰
python app.py
```

部署（例如 Render）時**一定要設定 `SECRET_KEY` 環境變數**，否則每次伺服器重啟，所有人都要重新登入。
可以用 `python -c "import secrets; print(secrets.token_hex(32))"` 產生一組。

**帳號安全**

- 密碼以 werkzeug 雜湊儲存；舊帳號的明文密碼會在下次登入時自動換成雜湊。
- 忘記密碼要用「救援碼」重設：註冊時顯示一次（伺服器只存雜湊），舊帳號在下次登入時補發。
- 登入或重設密碼，同一個帳號 10 分鐘內錯 5 次就暫時鎖住。
- 戰績、好友、改資料、建房／入房都靠登入 token 認人，前端送來的 user_id 不再被採信。
- 線上對局的每一步都由伺服器用棋規驗證，改封包作弊會被拒絕並同步回正確盤面。

**測試**

```bash
python tests/run_all.py            # 全部跑一次（約 1 分鐘；需要 pip install -r requirements.txt 和 Node.js，不需要 MongoDB）
python tests/run_all.py --stress   # 連壓力測試一起跑（再加 2～3 分鐘）

# 也可以單獨跑
node tests/rules.test.mjs          # 前端棋規
python tests/test_rules.py         # 後端棋規
python tests/test_validate.py      # 伺服器棋步驗證（防作弊）
python tests/test_client_parity.py # 前端實際送出的動作伺服器都接受
python tests/test_api.py           # HTTP API 邊界／資安
python tests/test_server.py        # 房間／同步／語音信令
python tests/test_history_dedupe.py
node tests/lobby_xss.test.mjs      # 好友列表 XSS
python tests/stress_test.py --rooms 10,50,100,200 --seconds 15   # 壓力測試，結果存到 tests/stress_results.json
python tests/packet_report.py --games 10   # 封包大小、延遲、計時穩定度、斷線重連、作弊封包，結果存到 tests/packet_results.json
```

量測結果與解讀整理在 [`docs/測試數據.md`](docs/測試數據.md)。

**封包紀錄器**：連線對局頁網址加 `&netlog=1`（或按 Ctrl + Shift + L），右下角會即時顯示每個封包的往返時間、大小、
計時同步間隔、斷線重連時間，可以下載 CSV。主控台也能用 `wallgoNetLog.summary()`。

改棋規時，在 `tests/rule_cases.json` 加一個盤面案例，前後端兩支測試都要通過。

**AI 訓練**

```bash
cd ai-training
npm install
node train.js            # 自我對弈訓練
node verify_fixes.mjs    # 回歸測試
node eval_vs_random.mjs alpha_model 20 100   # 對隨機對手評估
```

訓練現況與已知問題記在 `ai-training/FINDINGS.md`：MCTS 換手、破牆特徵、
2 步移動等五項 bug 已修正，但第 2–10 輪 180 局中新模型只有 36% 勝率，
策略熵持續上升 —— 詳細診斷與後續方向見該檔。

網頁端的 AI 對手目前用的是 `js/game/ai.js` 的啟發式邏輯，
**尚未接上這裡訓練出來的模型**。

## 語音（WebRTC）

連線對局右下角的 🎤 按鈕。開麥的人會對房內每個人各建一條點對點連線送出聲音，
沒開麥的人（包括觀戰者）也聽得到；配對資訊透過自己的 Socket.IO 伺服器轉送（`voice_signal` 事件），聲音本身不經過伺服器。

- 麥克風只在 **https** 或 **localhost** 下可用，這是瀏覽器的安全限制。
- 目前只設定了 STUN。不同電信、公司網路之間可能連不上，需要在 `js/config.js` 的 `RTC_CONFIG` 加 TURN 伺服器。

## 授權

背景音樂 **Carefree** by Kevin MacLeod（[incompetech.com](https://incompetech.com/music/royalty-free/index.html?isrc=USUAN1100199)），
授權 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。

音效出自 **Kenney** 的 [Casino Audio](https://kenney.nl/assets/casino-audio) 與
[Impact Sounds](https://kenney.nl/assets/impact-sounds)，授權
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)。
