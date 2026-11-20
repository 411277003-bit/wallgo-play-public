// 大廳啟動：所有 script 載入、頁面載好之後才執行
// （大廳的 script 都是一般 <script>，共用全域變數；載入順序寫在 index.html）

window.onload = () => {
  checkLogin();
  syncSettingsUI();
  if (currentUser) { loadHistory(); loadGlobalStats(); }
};
