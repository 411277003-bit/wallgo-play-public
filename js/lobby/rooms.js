// 開局：單機（人數、規則版本）、線上房間（建立／加入／觀戰／開始）
// （大廳的 script 都是一般 <script>，共用全域變數；載入順序寫在 index.html）

/* ═════════ 單機遊戲 ═════════ */
function setPlayers(val){
  selectedPlayers = val;
  localStorage.setItem('wallGoPlayers', val);
  document.querySelectorAll('#solo-chips .chip').forEach(c=>{
    c.setAttribute('aria-pressed', String(c.dataset.val) === String(val) ? 'true' : 'false');
  });
}
document.querySelectorAll('#solo-chips .chip').forEach(c=>{
  c.onclick=()=>setPlayers(c.dataset.val === 'ai' ? 'ai' : Number(c.dataset.val));
});
function openSoloModal(){ setPlayers(selectedPlayers); setRule(selectedRule); openModal('solo-modal'); }
function startGame(){ window.location.href = `game.html?players=${selectedPlayers}&rules=${selectedRule}`; }

/* 規則版本：1 = 原版，2 = 圓方棋 */
let selectedRule = localStorage.getItem('wallGoRule') === '2' ? 2 : 1;
function setRule(val){
  selectedRule = Number(val) === 2 ? 2 : 1;
  localStorage.setItem('wallGoRule', String(selectedRule));
  document.querySelectorAll('.rule-chips .chip').forEach(c=>{
    c.setAttribute('aria-pressed', Number(c.dataset.rule) === selectedRule ? 'true' : 'false');
  });
}
document.querySelectorAll('.rule-chips .chip').forEach(c=>{ c.onclick=()=>setRule(c.dataset.rule); });
setRule(selectedRule);

/* ═════════ 線上房間 ═════════ */
function openRoomModal(){
  openModal('room-modal');
  document.getElementById('room-ui-main').style.display = 'block';
  document.getElementById('room-ui-waiting').style.display = 'none';
}

function createRoom(){
  const roomCode = Math.floor(1000 + Math.random() * 9000).toString();
  const userInfo = { id: currentUser.id, name: currentUser.name, avatar: currentUser.avatar };
  currentRoomCode = roomCode;
  socket.emit('create_room', { room_code: roomCode, user_info: userInfo, rules: selectedRule });
}

function joinRoom(){
  const roomCode = document.getElementById('join-room-input').value.trim();
  if (roomCode.length !== 4) return toast('請輸入 4 位數字的房間代碼！');
  const userInfo = { id: currentUser.id, name: currentUser.name, avatar: currentUser.avatar };
  currentRoomCode = roomCode;
  socket.emit('join_room', { room_code: roomCode, user_info: userInfo });
}

function spectateRoom(){
  const roomCode = document.getElementById('join-room-input').value.trim();
  if (roomCode.length !== 4) return toast('請輸入 4 位數字的房間代碼！');
  socket.emit('spectate_room', { room_code: roomCode });
}
socket.on('spectate_ok', (data) => {
  window.location.href = `game.html?mode=online&room=${data.room_code}&players=${data.player_count}&rules=${data.rules || 1}&spectate=1`;
});

function leaveRoom(){
  if (currentRoomCode) {
    socket.emit('leave_room', { room_code: currentRoomCode, user_id: currentUser.id });
    currentRoomCode = null;
  }
  openRoomModal();
}

socket.on('room_created', (data) => {
  currentRoomCode = data.room_code;
  renderWaitingRoom(data.room_code, data.players, data.rules);
});

socket.on('room_updated', (data) => {
  if (currentRoomCode === data.room_code) renderWaitingRoom(data.room_code, data.players, data.rules);
});

socket.on('join_error', (data) => {
  toast(data.message);
  currentRoomCode = null;
});

function renderWaitingRoom(code, players, rules){
  openModal('room-modal');
  document.getElementById('room-ui-main').style.display = 'none';
  document.getElementById('room-ui-waiting').style.display = 'block';

  document.getElementById('display-room-code').innerText = code;
  document.getElementById('room-rule-label').innerText = `（牆壁圍棋 ${rules === 2 ? 2 : 1}）`;
  document.getElementById('room-player-count').innerText = players.length;

  const list = document.getElementById('room-players-list');
  list.innerHTML = players.map(p => `
    <div class="pitem">
      <div class="ava">${esc(p.avatar)}</div>
      <div>
        <div class="nm">${esc(p.name)} ${p.id === currentUser.id ? '（你）' : ''}</div>
        <div class="idz">${esc(p.id)}</div>
      </div>
    </div>`).join('');

  document.getElementById('btn-start-online').disabled = (players.length < 2);
}

function startOnlineGame(){
  if (currentRoomCode) socket.emit('start_game', { room_code: currentRoomCode });
}

socket.on('game_started', (data) => {
  window.location.href = `game.html?mode=online&room=${data.room_code}&players=${data.player_count}&rules=${data.rules || 1}`;
});
