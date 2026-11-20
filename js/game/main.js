// 對局頁進入點：畫面按鈕、Vue 元件組裝、啟動
import { TURN_TIME_LIMIT } from '../config.js';
import { boardSize, isOnline, isVsAI, aiColor, colorMap, phaseNames, quickMsgs, S, key, currentColor, suffixOf, getDisplayName, getValidWalls, nextShape, movesForPiece, breakableWalls } from './state.js';
import { sendMsg, sendChat, mentionOptions, pickMention, splitMention } from './chat.js';
import { initOnline } from './online.js';
import { resetGame, handleCellClick, handleWallClick, toggleWallBreaker } from './flow.js';
import { toggleMic } from './voice.js';
const { createApp, computed } = Vue;

// ── 其他介面動作 ──
function backToMenu() { window.location.href = 'index.html'; }
function toggleChat() {
    S.chatOpen = !S.chatOpen;
    if (S.chatOpen) S.unread = false;
    document.body.classList.toggle('chat-open', S.chatOpen);
}
function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {});
}
document.addEventListener('fullscreenchange', () => {
    S.fullscreen = !!document.fullscreenElement;
    S.hudCollapsed = S.fullscreen;   // 進入全螢幕時收起右下按鈕，離開時恢復
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { S.showResult = false; S.confirmReset = false; S.confirmBreak = false; if (S.chatOpen) toggleChat(); }
});

// ══════════ Vue ══════════
createApp({
    setup() {
        const curColor = computed(() => currentColor());
        const phaseLabel = computed(() => phaseNames[S.phase] || '');
        // 規則 2 放置期：輪到的人這次要放哪種棋
        const curShape = computed(() => S.phase === 'placement' && curColor.value ? nextShape(curColor.value) : undefined);

        const isAITurn = computed(() => isVsAI && curColor.value === aiColor && S.phase !== 'game_over');
        const canUseBreaker = computed(() => {
            const c = curColor.value;
            if (!c || S.isProcessing || isAITurn.value) return false;
            if (isOnline && c !== S.myOnlineColor) return false;
            if (S.phase === 'wall_breaking') return true;
            return S.phase === 'movement' && S.stepsTaken === 0 && !!(S.playersInfo[c] && S.playersInfo[c].hasBreaker);
        });

        const cells = computed(() => {
            const cc = curColor.value;
            const moveSet = new Set(), wallSet = new Set();
            if (S.phase === 'movement' && S.selectedPieceIndex !== -1) {
                const p = S.pieces[S.selectedPieceIndex];
                if (p) movesForPiece(p).forEach(m => moveSet.add(key(m.r, m.c)));
            } else if (S.phase === 'wall_building') {
                const p = S.pieces[S.movedPieceIndex];
                if (p) getValidWalls(p.r, p.c).forEach(w => wallSet.add(key(w.r, w.c)));
            } else if (S.phase === 'wall_breaking') {
                breakableWalls(cc).forEach(k => wallSet.add(k));
            }
            const pieceAt = new Map();
            S.pieces.forEach((p, i) => pieceAt.set(key(p.r, p.c), i));

            const out = [];
            for (let r = 0; r < boardSize; r++) {
                for (let c = 0; c < boardSize; c++) {
                    const k = key(r, c);
                    const cls = [];
                    let type, piece = null;
                    if (r % 2 === 0 && c % 2 === 0) {
                        type = 'cell'; cls.push('cell');
                        if (moveSet.has(k)) cls.push('highlight');
                        if (S.phase === 'game_over' && S.territories.has(k)) cls.push('territory-' + S.territories.get(k));
                        if (pieceAt.has(k)) {
                            const i = pieceAt.get(k);
                            piece = { color: S.pieces[i].color, shape: S.pieces[i].shape, selected: i === S.selectedPieceIndex || i === S.movedPieceIndex };
                        }
                    } else if (r % 2 === 1 && c % 2 === 1) {
                        type = 'intersection'; cls.push('intersection');
                    } else {
                        type = 'wall'; cls.push(r % 2 === 1 ? 'wall-h' : 'wall-v');
                        if (S.walls.has(k)) {
                            cls.push('wall-placed', 'wall-' + S.walls.get(k));
                            if (S.phase === 'wall_breaking' && !wallSet.has(k)) cls.push('wall-dim');
                        }
                        if (wallSet.has(k)) cls.push('highlight-wall');
                    }
                    out.push({ key: k, r, c, type, cls, piece });
                }
            }
            return out;
        });

        function onCellClick(cell) {
            if (cell.type === 'cell') handleCellClick(cell.r, cell.c);
            else if (cell.type === 'wall') handleWallClick(cell.r, cell.c);
        }

        return {
            S, colorMap, quickMsgs, TURN_TIME_LIMIT, isOnline,
            curColor, curShape, phaseLabel, canUseBreaker, cells,
            mentionOptions, pickMention, splitMention, onCellClick,
            nameOf: (c) => getDisplayName(c),
            tagOf: (c) => suffixOf(c),
            timeOf: (c) => Math.max(0, S.playerTimes[c] ?? TURN_TIME_LIMIT),
            hasBreaker: (c) => !!(S.playersInfo[c] && S.playersInfo[c].hasBreaker),
            resetGame, toggleWallBreaker, toggleChat, toggleMic, toggleFullscreen, backToMenu,
            sendMsg, sendChat
        };
    }
}).mount('#app');

// 棋盤上緣要讓出上方 HUD（階段旗、回合列、按鈕）的實際高度。
// 這些元件會隨螢幕大小、字型載入而變高，用量的比用 CSS 猜準，才不會壓到棋盤。
function fitStageToHud() {
    let bottom = 0;
    document.querySelectorAll('.hud-top > *, .hud-tl > *, .hud-br > *').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.height && r.top < window.innerHeight / 3) bottom = Math.max(bottom, r.bottom);
    });
    if (bottom) document.documentElement.style.setProperty('--hud-top', `${Math.ceil(bottom + 10)}px`);
}
const hudObserver = new ResizeObserver(fitStageToHud);
document.querySelectorAll('.hud-top, .hud-tl, .hud-br').forEach(el => hudObserver.observe(el));
window.addEventListener('resize', fitStageToHud);
if (document.fonts) document.fonts.ready.then(fitStageToHud);
fitStageToHud();

initOnline();
resetGame(false);
