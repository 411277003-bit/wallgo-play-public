// 設定：背景音樂、開場音效、音樂開關
// （大廳的 script 都是一般 <script>，共用全域變數；載入順序寫在 index.html）

/* ═════════ 設定 / 音樂 ═════════ */
/* 音樂／音效開關只在「設定」裡切換 */
let MUSIC_OFF = localStorage.getItem('wallGoMusic') === 'off';

/* 背景音樂：assets/bgm.mp3（Carefree — Kevin MacLeod, CC BY 4.0）。
   瀏覽器一律禁止未經互動的自動播放，所以真正開聲是在第一次點擊／按鍵時。 */
const BGM_VOLUME = 0.16;
const bgmEl = document.getElementById('bgm');

function musicOn(){ return !MUSIC_OFF; }

function startMusic(){
  if (!musicOn()) return;
  bgmEl.volume = BGM_VOLUME;
  bgmEl.play().catch(err => console.warn('背景音樂無法播放：', err));
}

function stopMusic(){ bgmEl.pause(); }

/* 音效：Kenney 的 CC0 音效包，跟著背景對局動畫觸發。
   與背景音樂共用同一顆 🔈 開關。 */
/* HTMLAudioElement.volume 的上限是 1，破牆聲要比其他音更重，就靠 layers：
   同時播放多份同一個取樣來疊出音壓。
   （不走 Web Audio 的 GainNode 是因為 createMediaElementSource 接上後
     聲音只走那條路徑 —— AudioContext 停在 suspended、或以 file:// 開啟
     導致來源被 taint 時，結果是完全沒聲音而且不會拋例外。） */
/* stagger 決定疊幾層、每層延遲幾毫秒起播。前兩層同時下去給衝擊力，
   其餘錯開十幾毫秒撐出厚度，比單純同時播五份更像一記重擊而非破音。 */
const SFX = {
  move:  { src: 'assets/sfx/piece-move.ogg', vol: 0.26, stagger: [0] },              /* 圓柱棋子落定 */
  wall:  { src: 'assets/sfx/wall-build.ogg', vol: 0.46, stagger: [0] },              /* 木板立起 */
  break: { src: 'assets/sfx/wall-break.ogg', vol: 1.00, stagger: [0,0,14,30,48] },   /* 重擊破牆 */
};
const sfxEls = {};
for (const [name, { src, vol, stagger }] of Object.entries(SFX)) {
  sfxEls[name] = stagger.map(() => {
    const a = new Audio(src);
    a.preload = 'auto';
    a.volume = vol;
    return a;
  });
}

/* 音效只服務登入前的開場動畫。introStage 在開場結束時被設回 null，
   之後大廳的背景對局就回到只有背景音樂的狀態。 */
function playSfx(name){
  if (introStage === null || !musicOn()) return;
  const group = sfxEls[name];
  if (!group) return;
  const { stagger } = SFX[name];
  group.forEach((a, i) => {
    const fire = () => { a.currentTime = 0; a.play().catch(() => {}); };
    if (stagger[i]) setTimeout(fire, stagger[i]); else fire();
  });
}

['pointerdown', 'keydown'].forEach(ev =>
  window.addEventListener(ev, () => startMusic(), { once: true, passive: true }));
