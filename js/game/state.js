// 對局頁的共用狀態：網址參數、登入資訊、畫面狀態 S、顯示用小工具，以及綁好 S 的棋規函式
import * as Rules from '../shared/rules.js';
const { reactive } = Vue;

export const boardSize = Rules.BOARD_SIZE;
export const urlParams = new URLSearchParams(window.location.search);
export const paramPlayers = urlParams.get('players');
export const mode = urlParams.get('mode');
export const roomCode = urlParams.get('room');
export const isOnline = mode === 'online';
export const wantSpectate = isOnline && urlParams.get('spectate') === '1';
export const urlRules = urlParams.get('rules') === '2' ? 2 : 1;
export const isVsAI = paramPlayers === 'ai';
export const playerCount = isVsAI ? 2 : (parseInt(paramPlayers) || 3);
export const aiColor = isVsAI ? 'blue' : null;
export const session = JSON.parse(localStorage.getItem('wallGoSession'));
export const myName = session ? session.name : '';

export const allColors = Rules.ALL_COLORS;
export const colorMap = {
    red:    { color: 'var(--color-red)',    icon: '🔴', text: '紅色' },
    blue:   { color: 'var(--color-blue)',   icon: '🔵', text: '藍色' },
    yellow: { color: 'var(--color-yellow)', icon: '🟡', text: '黃色' },
    green:  { color: 'var(--color-green)',  icon: '🟢', text: '綠色' }
};
export const phaseNames = { placement: '放置', movement: '移動', wall_building: '建牆', wall_breaking: '破牆', game_over: '結束' };
export const quickMsgs = ['👋 你好！', '😎 這局穩了！', '😱 阿幹按錯！', '🐮 牛喔放這裡！', '🤔 讓我想想...', '🔥 太神啦！', '⏱️ 快點下棋啦！', '😭 完蛋了...'];

// ── 所有會反映到畫面的狀態都放在這個 reactive 物件 ──
export const S = reactive({
    phase: 'placement',
    activeColors: [], placementQueue: [], movementOrder: [],
    turnIndex: 0,
    pieces: [],
    walls: new Map(),
    territories: new Map(),
    playersInfo: {},
    playerTimes: {},
    stepsTaken: 0,
    selectedPieceIndex: -1,
    movedPieceIndex: -1,
    isProcessing: false,
    myOnlineColor: null,
    colorToName: {},
    // 介面狀態
    chat: [], chatInput: '', chatOpen: false, unread: false,
    micOn: false, fullscreen: false, hudCollapsed: false,
    spectator: wantSpectate, spectators: [],
    rules: urlRules,      // 1 = 原版；2 = 每人一圓一方，方形只能直走，破牆限棋子四周
    moveDir: null,        // 規則 2 方形棋第一步的方向 [dr, dc]，第二步只能同方向
    gameId: '',           // 這一局的編號：連線時由伺服器發、全房共用；存戰績時用來避免同一局存兩次
    toast: '', result: null, showResult: false, confirmReset: false, confirmBreak: false
});

let toastTimer = null;

if (!isOnline) {
    S.colorToName.red = session ? session.name : '玩家1';
    if (isVsAI) S.colorToName.blue = '電腦 AI';
    else Object.assign(S.colorToName, { blue: '玩家2', yellow: '玩家3', green: '玩家4' });
}

// ── 小工具 ──
export const plain = (x) => JSON.parse(JSON.stringify(x));
export const key = Rules.key;
export function currentColor() {
    if (S.phase === 'game_over') return null;
    return S.phase === 'placement' ? S.placementQueue[S.turnIndex] : S.movementOrder[S.turnIndex];
}
export function isMe(c) { return isOnline ? c === S.myOnlineColor : c === 'red'; }
export function suffixOf(c) { return isMe(c) ? ' (你)' : (isVsAI && c === aiColor ? ' (AI)' : ''); }
export function getDisplayName(c) {
    let name = S.colorToName[c] || (colorMap[c] ? colorMap[c].text : '');
    if (name.length > 6) name = name.substring(0, 5) + '..';
    return name;
}
export function showToast(msg) {
    S.toast = msg;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { S.toast = ''; }, 2200);
}
// 棋規都在 js/shared/rules.js；這裡只是把目前的對局狀態 S 帶進去
export const getPieceIndexAt = (r, c) => Rules.pieceIndexAt(S, r, c);
export const getValidMoves = (r, c) => Rules.validMoves(S, r, c);
export const getValidWalls = (r, c) => Rules.validWalls(S, r, c);
export const nextShape = (color) => Rules.nextShape(S, color);
export const newPiece = (color, r, c) => Rules.newPiece(S, color, r, c);
export const movesForPiece = (p) => Rules.movesForPiece(S, p);
export const breakableWalls = (color) => Rules.breakableWalls(S, color);
export const evaluateBoard = (forColor) => Rules.evaluateBoard(S, forColor);
