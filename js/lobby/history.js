// 歷史戰績、全站統計、覆盤播放器
// （大廳的 script 都是一般 <script>，共用全域變數；載入順序寫在 index.html）

/* ═════════ 歷史戰績 ═════════ */
function openHistoryModal(){ openModal('history-modal'); loadHistory(); }

async function loadHistory(){
  if (!currentUser) return;
  const listEl = document.getElementById('history-list');

  try {
    const response = await fetch(`${API_URL}/api/get_history`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUser.id })
    });
    const result = await response.json();
    if (!result.success) return;

    const history = result.history;
    globalHistoryData = history;
    let wins = 0;

    let localReplays = {};
    try { localReplays = JSON.parse(localStorage.getItem('wallGoReplays') || '{}'); } catch(e) {}

    if (history.length === 0) {
      renderStats(0, 0);
      listEl.innerHTML = '<div class="empty">尚無比賽紀錄<br>趕快開始第一場對戰吧！</div>';
      document.getElementById('menu-history-sub').innerText = '尚無對局紀錄';
      return;
    }

    let rows = '';
    history.slice().reverse().forEach((record, revIdx) => {
      const originalIndex = history.length - 1 - revIdx;
      if (record.winner.includes('(你)')) wins++;

      const recordKey = record.winScore + '_' + (record.details || '').replace(/\s+/g, '');
      if (!record.replayData && localReplays[recordKey]) {
        record.replayData = localReplays[recordKey];
        globalHistoryData[originalIndex].replayData = localReplays[recordKey];
      }

      const replayBtn = record.replayData
        ? `<button class="mini" onclick="openReplay(${originalIndex})">查看覆盤</button>`
        : `<span class="idz">無覆盤</span>`;

      rows += `
        <div class="hitem">
          <div>
            <div class="hd">${esc(record.date)}</div>
            <div class="hw">${esc(record.winner)} <span class="hs">（${esc(String(record.winScore))} 格）</span></div>
            <div class="hs">${esc(record.details || '')}</div>
          </div>
          <div class="act">${replayBtn}</div>
        </div>`;
    });
    listEl.innerHTML = rows;

    renderStats(history.length, wins);
  } catch (error) {
    listEl.innerHTML = '<div class="empty" style="color:var(--rust)">戰績載入失敗，請檢查連線。</div>';
  }
}

function renderStats(total, wins){
  const rate = total ? Math.round((wins / total) * 100) : 0;
  /* 弧長＝勝率；0 時圓頭線帽仍會畫出一個點，直接藏起來 */
  const arc = document.getElementById('me-rate-arc');
  arc.style.strokeDasharray = `${rate} 100`;
  arc.style.opacity = rate ? 1 : 0;

  document.getElementById('me-total').innerText = total;
  document.getElementById('me-wins').innerText = wins;
  document.getElementById('me-loses').innerText = total - wins;
  document.getElementById('me-rate').innerText = rate;
  document.getElementById('menu-history-sub').innerText = `${total} 場對局 ・ 勝率 ${rate}%`;
}

/* 側欄兩張卡片顯示全站統整數據（所有玩家），不是自己的戰績 */
async function loadGlobalStats(){
  const feed = document.getElementById('feed-list');
  try {
    const res = await fetch(`${API_URL}/api/global_stats`);
    const g = await res.json();
    if (!g.success) throw new Error();
    document.getElementById('g-total').innerText = g.totalGames;
    document.getElementById('g-players').innerText = `${g.players} 人`;
    document.getElementById('g-best').innerText = `${g.bestScore} 格`;
    document.getElementById('g-avg').innerText = `${g.avgScore} 格`;
    feed.innerHTML = g.latest.length
      ? g.latest.slice(0, 3).map(r => `
        <li><span><b>${esc(r.winner)}</b> 以 ${esc(String(r.winScore))} 格圍地獲勝</span><em>${esc(String(r.date).split(' ')[0] || '')}</em></li>`).join('')
      : '<li><span>尚無戰報，開一局來寫下第一筆吧。</span></li>';
  } catch (e) {
    feed.innerHTML = '<li><span style="color:var(--rust)">戰報載入失敗，請檢查連線。</span></li>';
  }
}

async function clearHistory(){
  if (!confirm('確定要清除所有的歷史戰績嗎？雲端資料刪除後無法復原！')) return;
  try {
    await fetch(`${API_URL}/api/clear_history`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUser.id })
    });
    localStorage.removeItem('wallGoReplays');
    loadHistory();
    toast('已清除所有戰績紀錄');
  } catch (error) { toast('清除失敗，請檢查連線！'); }
}

/* ═════════ 覆盤播放器 ═════════ */
let currentReplayData = [];
let currentStepIndex = 0;
const replayBoardSize = 13;

function openReplay(historyIndex){
  const record = globalHistoryData[historyIndex];
  if (!record || !record.replayData) return toast('這局遊戲沒有紀錄到覆盤資料！');

  currentReplayData = JSON.parse(record.replayData);
  currentStepIndex = currentReplayData.length - 1;

  closeModal('history-modal');
  openModal('replay-modal');
  initReplayBoard();
  renderReplayStep();
}

function closeReplay(){
  closeModal('replay-modal');
  currentReplayData = [];
  openModal('history-modal');
}

function initReplayBoard(){
  const boardEl = document.getElementById('replay-board');
  boardEl.innerHTML = '';
  for (let r = 0; r < replayBoardSize; r++) {
    for (let c = 0; c < replayBoardSize; c++) {
      const div = document.createElement('div');
      div.classList.add('grid-item');
      div.dataset.r = r; div.dataset.c = c;

      if (r % 2 === 0 && c % 2 === 0) div.classList.add('cell');
      else if (r % 2 !== 0 && c % 2 === 0) div.classList.add('wall-h');
      else if (r % 2 === 0 && c % 2 !== 0) div.classList.add('wall-v');
      else div.classList.add('intersection');

      boardEl.appendChild(div);
    }
  }
}

/* 覆盤可循環：最後一步再按「下一步」回到第一步，第一步按「上一步」跳到最後一步 */
function changeReplayStep(delta){
  const n = currentReplayData.length;
  if (n < 2) return;
  currentStepIndex = (currentStepIndex + delta + n) % n;
  renderReplayStep();
}

function renderReplayStep(){
  const boardEl = document.getElementById('replay-board');
  const stepData = currentReplayData[currentStepIndex];

  boardEl.querySelectorAll('.grid-item').forEach(el => {
    el.innerHTML = '';
    el.classList.remove('wall-placed','wall-red','wall-blue','wall-yellow','wall-green','wall-broken-highlight');
  });

  stepData.walls.forEach(wall => {
    const [wKey, color] = wall;
    const [wr, wc] = wKey.split(',').map(Number);
    const wEl = boardEl.querySelector(`[data-r="${wr}"][data-c="${wc}"]`);
    if (wEl) wEl.classList.add('wall-placed', `wall-${color}`);
  });

  /* 交叉點：四周有兩道以上的牆接進來，就把這格也填滿，牆才會連成一條沒有空隙 */
  const wallMap = new Map(stepData.walls);
  boardEl.querySelectorAll('.intersection').forEach(el => {
    const r = +el.dataset.r, c = +el.dataset.c;
    const joined = [[r-1,c],[r+1,c],[r,c-1],[r,c+1]].map(([y,x]) => wallMap.get(`${y},${x}`)).filter(Boolean);
    if (joined.length >= 2) el.classList.add('wall-placed', `wall-${joined[0]}`);
  });

  // 動態比對破牆：上一步有、這一步沒有的牆，標記為被打破
  if (currentStepIndex > 0) {
    const prevWalls = new Map(currentReplayData[currentStepIndex - 1].walls);
    const currWalls = new Map(stepData.walls);
    prevWalls.forEach((color, key) => {
      if (!currWalls.has(key)) {
        const [wr, wc] = key.split(',').map(Number);
        const wEl = boardEl.querySelector(`[data-r="${wr}"][data-c="${wc}"]`);
        if (wEl) wEl.classList.add('wall-broken-highlight');
      }
    });
  }

  stepData.pieces.forEach(p => {
    const cell = boardEl.querySelector(`[data-r="${p.r}"][data-c="${p.c}"]`);
    if (cell) {
      const pieceDiv = document.createElement('div');
      pieceDiv.classList.add('piece', `piece-${p.color}`);
      cell.appendChild(pieceDiv);
    }
  });

  document.getElementById('replay-step-display').innerText = `${currentStepIndex} / ${currentReplayData.length - 1}`;
  const prev = document.getElementById('btn-prev-step'), next = document.getElementById('btn-next-step');
  const last = currentReplayData.length - 1;
  prev.disabled = next.disabled = (last < 1);
  prev.style.opacity = next.style.opacity = prev.disabled ? '.45' : '1';
  /* 讓循環看得出來：在頭尾時按鈕文字提示會跳到哪裡 */
  prev.innerText = currentStepIndex === 0 ? '跳到最後' : '上一步';
  next.innerText = currentStepIndex === last ? '回到開頭' : '下一步';
}
