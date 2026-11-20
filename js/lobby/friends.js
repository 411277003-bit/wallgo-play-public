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
    const res = await fetch(`${API_URL}/api/get_friends`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUser.id })
    });
    const result = await res.json();
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
            <button class="mini ok" onclick="handleFriendReq('${esc(f.id)}','accept')">同意</button>
            <button class="mini no" onclick="handleFriendReq('${esc(f.id)}','reject')">拒絕</button>
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
          <div class="act"><button class="mini" onclick="inviteFriend('${esc(f.id)}')">邀請對戰</button></div>
        </div>`;
    });
    html += `</div>`;
  }

  document.getElementById('friend-list-render').innerHTML = html;
  document.getElementById('menu-friend-sub').innerText =
    `${friends.length} 位好友` + (pendingReceived.length ? ` ・ ${pendingReceived.length} 則待審核` : '');
}

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
    const res = await fetch(`${API_URL}/api/send_friend_request`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ requester_id: currentUser.id, receiver_id: targetId })
    });
    const result = await res.json();
    toast(result.message);
    if (result.success) {
      document.getElementById('add-friend-input').value = '';
      fetchFriends();
    }
  } catch(e) { toast('連線失敗，請稍後再試！'); }
}

async function handleFriendReq(requesterId, action){
  try {
    const res = await fetch(`${API_URL}/api/handle_friend_request`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ requester_id: requesterId, receiver_id: currentUser.id, action: action })
    });
    const result = await res.json();
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
