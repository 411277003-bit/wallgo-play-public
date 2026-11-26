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
    const result = await api('/api/login', { id: id, password: pwd });
    if (result.success) {
      currentUser = { ...result.user, token: result.token };
      localStorage.setItem('wallGoSession', JSON.stringify(currentUser));
      document.getElementById('login-pwd').value = '';
      // 舊帳號第一次登入：補發救援碼（忘記密碼時要用）
      if (result.recovery_code) showRecoveryCode(result.recovery_code, '已為你的帳號產生救援碼');
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
  if (name.length > 20) return toast('暱稱最多 20 個字。');
  if (pwd.length < 4) return toast('密碼至少要 4 個字。');
  let randomId = '#' + Math.floor(1000 + Math.random() * 9000);

  const btn = document.querySelector('#form-register .btn.gold');
  if (btn && btn.disabled) return;
  setBusy(btn, true, 'Signing up');
  try {
    const result = await api('/api/register', { id: randomId, username: name, password: pwd });
    if (result.success) {
      alert(`Sign-up complete!\n\nYour Player ID is: ${result.user.id}\nMake sure to remember your ID and password.`);
      showRecoveryCode(result.recovery_code, '註冊完成');
      currentUser = { ...result.user, token: result.token };
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
  document.getElementById('forgot-pwd-code').value = '';
  openModal('forgot-pwd-modal');
}

async function resetPassword(){
  const loginId = document.getElementById('forgot-pwd-id').value.trim();
  const code = document.getElementById('forgot-pwd-code').value.trim();
  const newPwd = document.getElementById('forgot-pwd-new').value.trim();

  if (!loginId || !code || !newPwd) return toast('請輸入 Player ID、救援碼和新密碼。');
  if (newPwd.length < 4) return toast('新密碼至少要 4 個字。');

  try {
    const result = await api('/api/reset_password', { id: loginId, recovery_code: code, new_password: newPwd });
    toast(result.message);
    if (result.success) {
      closeModal('forgot-pwd-modal');
      document.getElementById('login-pwd').value = '';
      showRecoveryCode(result.recovery_code, '密碼已重設，舊的救援碼已失效');
    }
  } catch (error) { toast('Can\'t reach the server. Please make sure the backend is running.'); }
}

/* 救援碼只會顯示這一次（伺服器只存雜湊），請玩家抄下來 */
function showRecoveryCode(code, title){
  if (!code) return;
  alert(`${title}\n\n你的救援碼：${code}\n\n忘記密碼時要用它重設，伺服器不會再顯示一次，請抄下來或截圖保存。`);
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
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem('wallGoSession')); } catch (e) {}
  // 舊版存的登入資料沒有 token，伺服器不再接受，請玩家重新登入一次
  if (saved && !saved.token) { localStorage.removeItem('wallGoSession'); saved = null; }
  if (saved) {
    currentUser = saved;
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
  if (newName.length > 20) return toast('暱稱最多 20 個字。');

  try {
    const result = await api('/api/update_profile', { username: newName, avatar: newAvatar || newName.charAt(0).toUpperCase() });
    if (!result.success) return toast(result.message);
    currentUser.name = result.user.name;
    currentUser.avatar = result.user.avatar;
    localStorage.setItem('wallGoSession', JSON.stringify(currentUser));
    updateProfileUI();
    closeModal('profile-modal');
    toast('個人資料已更新');
  } catch (e) { toast('連線失敗，個人資料沒有更新'); }
}
