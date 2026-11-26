// 好友系統：搜尋、邀請、接受／拒絕、列表
// （大廳的 script 都是一般 <script>，共用全域變數；載入順序寫在 index.html）

/* ═════════ 好友系統 ═════════ */
async function openFriendList(){
  openModal('friends-modal');
  document.getElementById('friend-list-render').innerHTML = '<p class="empty">載入中…</p>';
  await fetchFriends();
}

async function fetchFriends(){
  if (!currentUser) return;
  try {
    const result = await api('/api/get_friends', {});
    if (result.success) renderFriendsUI(result.friends, result.pending_sent, result.pending_received);
  } catch(e) {
    document.getElementById('friend-list-render').innerHTML = '<p class="empty" style="color:var(--rust)">載入失敗，請檢查連線。</p>';
  }
}

function renderFriendsUI(friends, pendingSent, pendingReceived){
  let html = '';

  if (pendingReceived.length > 0) {
    html += `<div class="grouplbl">待您審核的邀請</div><div class="rlist">`;
    pendingReceived.forEach(f => {
      html += `
        <div class="pitem" style="border-color:var(--brass)">
          <div class="ava">${esc(f.avatar)}</div>
          <div><div class="nm">${esc(f.name)}</div><div class="idz">${esc(f.id)}</div></div>
          <div class="act">
            <button class="mini ok" data-friend-action="accept" data-id="${esc(f.id)}">同意</button>
            <button class="mini no" data-friend-action="reject" data-id="${esc(f.id)}">拒絕</button>
          </div>
        </div>`;
    });
    html += `</div>`;
  }

  if (pendingSent.length > 0) {
    html += `<div class="grouplbl">等待對方同意</div><div class="rlist">`;
    pendingSent.forEach(f => {
      html += `
        <div class="pitem" style="opacity:.6">
          <div class="ava">${esc(f.avatar)}</div>
          <div><div class="nm">${esc(f.name)}</div><div class="idz">${esc(f.id)}</div></div>
          <div class="act"><span class="idz">等待中…</span></div>
        </div>`;
    });
    html += `</div>`;
  }

  html += `<div class="grouplbl">我的正式好友</div>`;
  if (friends.length === 0) {
    html += `<p class="empty">目前還沒有好友喔！<br>輸入上方 ID 加朋友吧。</p>`;
  } else {
    html += `<div class="rlist">`;
    friends.forEach(f => {
      html += `
        <div class="pitem">
          <div class="ava">${esc(f.avatar)}</div>
          <div><div class="nm">${esc(f.name)}<span class="dot"></span></div><div class="idz">${esc(f.id)}</div></div>
          <div class="act"><button class="mini" data-friend-action="invite" data-id="${esc(f.id)}">邀請對戰</button></div>
        </div>`;
    });
    html += `</div>`;
  }

  document.getElementById('friend-list-render').innerHTML = html;
  document.getElementById('menu-friend-sub').innerText =
    `${friends.length} 位好友` + (pendingReceived.length ? ` ・ ${pendingReceived.length} 則待審核` : '');
}

/* 好友列表的按鈕：不把 ID 塞進 onclick 字串（ID 裡的引號會變成程式碼，造成 XSS），
   改成放在 data-id 屬性，由這裡統一處理點擊；dataset 讀回來的永遠只是文字 */
document.getElementById('friend-list-render').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-friend-action]');
  if (!btn) return;
  const id = btn.dataset.id, action = btn.dataset.friendAction;
  if (action === 'invite') inviteFriend(id);
  else handleFriendReq(id, action);
});

function inviteFriend(friendId){
  closeModal('friends-modal');
  openRoomModal();
  createRoom();
  toast(`房間建立後，把代碼傳給 ${friendId} 就能入座！`);
}

async function sendFriendRequest(){
  const targetId = document.getElementById('add-friend-input').value.trim();
  if (!targetId.startsWith('#')) return toast('ID 格式錯誤（需包含 #，例如 #1234）');

  try {
    const result = await api('/api/send_friend_request', { receiver_id: targetId });
    toast(result.message);
    if (result.success) {
      document.getElementById('add-friend-input').value = '';
      fetchFriends();
    }
  } catch(e) { toast('連線失敗，請稍後再試！'); }
}

async function handleFriendReq(requesterId, action){
  try {
    const result = await api('/api/handle_friend_request', { requester_id: requesterId, action: action });
    if (result.success) fetchFriends();
    else toast(result.message);
  } catch(e) { toast('連線失敗！'); }
}

function toggleMusic(){
  MUSIC_OFF = !MUSIC_OFF;
  const off = MUSIC_OFF;
  localStorage.setItem('wallGoMusic', off ? 'off' : 'on');
  if (off) stopMusic(); else startMusic();
  toast(off ? '音樂與音效已關閉' : '音樂與音效已開啟');
  syncSettingsUI();
}

function syncSettingsUI(){
  document.getElementById('set-anim').setAttribute('aria-checked', String(!REDUCED));
  document.getElementById('set-music').setAttribute('aria-checked', String(!MUSIC_OFF));
}
