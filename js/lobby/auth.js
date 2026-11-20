// 登入、註冊、忘記密碼、開場結束後滑入大廳、編輯資料、登出
// （大廳的 script 都是一般 <script>，共用全域變數；載入順序寫在 index.html）

/* ═════════ 登入 / 註冊 ═════════ */
function switchAuthTab(type){
  const tabs = document.querySelectorAll('.tab');
  document.querySelectorAll('.form').forEach(f=>f.classList.remove('active'));
  tabs.forEach(t=>t.classList.remove('active'));
  if (type === 'login'){ tabs[0].classList.add('active'); document.getElementById('form-login').classList.add('active'); }
  else { tabs[1].classList.add('active'); document.getElementById('form-register').classList.add('active'); }
}

/* 送出登入／註冊時，按鈕立刻給回饋並鎖住，避免等待伺服器時像沒反應、或被重複送出 */
function setBusy(btn, busy, label){
  if(!btn) return;
  if(busy){ btn.dataset.label = btn.textContent; btn.textContent = label; btn.disabled = true; btn.classList.add('busy'); }
  else { btn.textContent = btn.dataset.label || btn.textContent; btn.disabled = false; btn.classList.remove('busy'); }
}

async function performLogin(){
  const id = document.getElementById('login-id').value.trim();
  const pwd = document.getElementById('login-pwd').value.trim();

  if (!id || !pwd) return toast('Please enter both your ID and password.');
  if (!id.startsWith('#')) return toast('Invalid ID — it must start with # (e.g. #1234).');

  const btn = document.querySelector('#form-login .btn.gold');
  if (btn && btn.disabled) return;
  setBusy(btn, true, 'Logging in');
  try {
    const response = await fetch(`${API_URL}/api/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id, password: pwd })
    });
    const result = await response.json();
    if (result.success) {
      currentUser = { ...result.user };
      localStorage.setItem('wallGoSession', JSON.stringify(currentUser));
      document.getElementById('login-pwd').value = '';
      checkLogin();
      loadHistory(); loadGlobalStats();
    } else toast(result.message);
  } catch (error) { toast('Can\'t reach the server. Please make sure the backend is running.'); }
  finally { setBusy(btn, false); }
}

async function performRegister(){
  const name = document.getElementById('reg-name').value.trim();
  const pwd = document.getElementById('reg-pwd').value.trim();

  if (!name || !pwd) return toast('Please enter both a nickname and a password.');
  let randomId = '#' + Math.floor(1000 + Math.random() * 9000);

  const btn = document.querySelector('#form-register .btn.gold');
  if (btn && btn.disabled) return;
  setBusy(btn, true, 'Signing up');
  try {
    const response = await fetch(`${API_URL}/api/register`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: randomId, username: name, password: pwd })
    });
    const result = await response.json();
    if (result.success) {
      alert(`Sign-up complete!\n\nYour Player ID is: ${result.user.id}\nMake sure to remember your ID and password.`);
      currentUser = { ...result.user };
      localStorage.setItem('wallGoSession', JSON.stringify(currentUser));
      document.getElementById('reg-name').value = '';
      document.getElementById('reg-pwd').value = '';
      checkLogin();
      loadHistory(); loadGlobalStats();
    } else toast(result.message);
  } catch (error) { toast('Can\'t reach the server. Please make sure the backend is running.'); }
  finally { setBusy(btn, false); }
}

function handleForgotPassword(){
  const loginId = document.getElementById('login-id').value.trim();
  if (loginId) document.getElementById('forgot-pwd-id').value = loginId;
  document.getElementById('forgot-pwd-new').value = '';
  openModal('forgot-pwd-modal');
}

async function resetPassword(){
  const loginId = document.getElementById('forgot-pwd-id').value.trim();
  const newPwd = document.getElementById('forgot-pwd-new').value.trim();

  if (!loginId || !newPwd) return toast('Please enter both your Player ID and a new password.');

  try {
    const response = await fetch(`${API_URL}/api/reset_password`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: loginId, new_password: newPwd })
    });
    const result = await response.json();
    toast(result.message);
    if (result.success) {
      closeModal('forgot-pwd-modal');
      document.getElementById('login-pwd').value = '';
    }
  } catch (error) { toast('Can\'t reach the server. Please make sure the backend is running.'); }
}

/* 登入／註冊表單按 Enter 直接送出 */
[['form-login', () => performLogin()], ['form-register', () => performRegister()]].forEach(([id, submit]) =>
  document.querySelectorAll(`#${id} input`).forEach(inp =>
    inp.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) submit(); })));

/* 開場動畫的接力點：畫布把牆打破時呼叫，UI 才開始滑入 */
function onIntroBreak(){
  setLayout(1);                       /* 棋盤讓到右半邊，左半邊留給登入卡 */
  const el=document.getElementById('auth-page');
  el.classList.remove('intro-wait');
  el.classList.add('intro-play');
  setTimeout(()=>el.classList.remove('intro-play'), 1800);
}

function checkLogin(){
  const savedSession = localStorage.getItem('wallGoSession');
  if (savedSession) {
    currentUser = JSON.parse(savedSession);
    document.getElementById('auth-page').classList.remove('on');
    document.getElementById('stage').classList.add('on');
    /* 大廳的 UI 左右都有，棋盤回到置中並縮到兩側 rail 之間 */
    inLobby = true;
    measureLobby();
    setLayout(0);
    applyLayout();
    updateProfileUI();
  } else {
    const el=document.getElementById('auth-page');
    /* 開場動畫播完前先藏著；不播動畫時直接顯示 */
    inLobby = false;
    const skipIntro = REDUCED || el.classList.contains('intro-play');
    if(!skipIntro) el.classList.add('intro-wait');
    el.classList.add('on');
    document.getElementById('stage').classList.remove('on');
    /* 不播開場就沒有過場，直接就定位；要在登入卡顯示之後才量得到它的尺寸 */
    if(skipIntro) setLayout(1, true);
  }
}

/* 登出要二次確認：第一次按只是把按鈕換成「確定登出／取消」 */
function askLogout(show){
  document.getElementById('logout-btn').hidden = show;
  document.getElementById('logout-confirm').hidden = !show;
}

function logout(){
  localStorage.removeItem('wallGoSession');
  location.reload();
}

function updateProfileUI(){
  document.getElementById('display-name').innerText = currentUser.name;
  document.getElementById('display-id').innerText = `ID: ${currentUser.id}`;
  document.getElementById('display-avatar').innerText = currentUser.avatar;
}

function openProfileEditor(){
  document.getElementById('profile-id').innerText = `編輯個人資料 ・ ID: ${currentUser.id}`;
  document.getElementById('input-name').value = currentUser.name;
  document.getElementById('input-avatar').value = currentUser.avatar;
  openModal('profile-modal');
}

async function saveProfile(){
  const newName = document.getElementById('input-name').value.trim();
  const newAvatar = document.getElementById('input-avatar').value.trim();
  if (!newName) return toast('暱稱不能為空！');

  currentUser.name = newName;
  currentUser.avatar = newAvatar || newName.charAt(0).toUpperCase();

  localStorage.setItem('wallGoSession', JSON.stringify(currentUser));
  updateProfileUI();
  closeModal('profile-modal');

  try {
    await fetch(`${API_URL}/api/update_profile`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: currentUser.id, username: currentUser.name, avatar: currentUser.avatar })
    });
    toast('個人資料已更新');
  } catch (e) { toast('已更新本機資料，但雲端同步失敗'); }
}
