// 大廳共用：提示訊息、對話框、登入狀態、socket 連線、左側選單、esc() 等小工具
// （大廳的 script 都是一般 <script>，共用全域變數；載入順序寫在 index.html）

/* ═════════ 共用 UI ═════════ */
const toastEl=document.getElementById('toast');
let tid;
function toast(msg){
  toastEl.textContent=msg; toastEl.classList.add('on');
  clearTimeout(tid); tid=setTimeout(()=>toastEl.classList.remove('on'),2400);
}

function openModal(id){ document.getElementById(id).classList.add('on'); }
function closeModal(id){ document.getElementById(id).classList.remove('on'); }
function closeAllModals(){ document.querySelectorAll('.scrim.on').forEach(s=>s.classList.remove('on')); }

document.querySelectorAll('.scrim').forEach(s=>{
  s.addEventListener('click', e=>{ if(e.target===s) s.classList.remove('on'); });
});
addEventListener('keydown', e=>{ if(e.key==='Escape') closeAllModals(); });

/* ═════════ 帳號 / 大廳資料 ═════════ */
let currentUser = null;
let selectedPlayers = localStorage.getItem('wallGoPlayers') || 3;
let globalHistoryData = [];

const { API_URL } = window.WALLGO_CONFIG;   // 設定在 js/config.js
const socket = io(API_URL);
let currentRoomCode = null;

socket.on('connect', ()=>{ const el=document.getElementById('conn-state'); if(el) el.textContent='已連線'; });
socket.on('disconnect', ()=>{ const el=document.getElementById('conn-state'); if(el) el.textContent='已斷線'; });

/* 左側選單 / 工具列 / 開始鍵 */
document.querySelectorAll('[data-act]').forEach(b=>b.onclick=()=>{
  const a=b.dataset.act;
  if(a==='solo')       openSoloModal();
  if(a==='room')       openRoomModal();
  if(a==='friend')     openFriendList();
  if(a==='history')    openHistoryModal();
  if(a==='me')         openProfileEditor();
  if(a==='settings')   { syncSettingsUI(); askLogout(false); openModal('settings-modal'); }
  if(a==='help')       openModal('rules-modal');
  if(a==='info')       openModal('info-modal');
});

/* ═════════ 小工具 ═════════ */
function esc(str){
  return String(str ?? '').replace(/[&<>"']/g, ch =>
    ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[ch]));
}
