// 對局流程：開局、計時、點棋盤、建牆／破牆、換手、結算
import * as Rules from '../shared/rules.js';
import '../config.js';
import { isOnline, isVsAI, playerCount, aiColor, session, allColors, colorMap, S, plain, key, currentColor, isMe, suffixOf, getDisplayName, showToast, getPieceIndexAt, getValidWalls, newPiece, movesForPiece, breakableWalls } from './state.js';
import { systemMsg } from './chat.js';
import { broadcastGameState } from './online.js';
import { executeAILogic, checkAITurn } from './ai.js';
const { API_URL, TURN_TIME_LIMIT } = window.WALLGO_CONFIG;

let moveHistory = [];
let finishedGameId = null;   // 這個頁面已經結算過的那一局，避免重新整理／重連後又結算、又存一次戰績
const newGameId = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
let clockInterval = null;

export function saveHistoryStep() {
    moveHistory.push({ pieces: plain(S.pieces), walls: Array.from(S.walls.entries()) });
}

// ── 對局流程 ──
export function resetGame(isManual) {
    if (clockInterval) { clearInterval(clockInterval); clockInterval = null; }
    S.activeColors = allColors.slice(0, playerCount);
    S.placementQueue = [...S.activeColors, ...[...S.activeColors].reverse()];
    S.movementOrder = [...S.activeColors];
    S.pieces = []; S.walls = new Map(); S.territories = new Map();
    const info = {}, times = {};
    S.activeColors.forEach(c => { info[c] = { hasBreaker: true }; times[c] = TURN_TIME_LIMIT; });
    S.playersInfo = info; S.playerTimes = times;
    S.phase = 'placement'; S.turnIndex = 0; S.selectedPieceIndex = -1; S.movedPieceIndex = -1; S.stepsTaken = 0; S.moveDir = null;
    S.isProcessing = false; S.result = null; S.showResult = false;
    S.gameId = newGameId();   // 連線對局會在收到伺服器狀態時換成全房共用的編號

    moveHistory = [];
    saveHistoryStep();
    startClock();
    checkAITurn();

    if (isOnline && isManual && !S.spectator) {
        broadcastGameState();
        systemMsg('🔄 已重新開始新的一局！', true);
    }
}

export function startClock() {
    if (clockInterval) clearInterval(clockInterval);
    clockInterval = null;
    if (S.phase === 'game_over') return;

    clockInterval = setInterval(() => {
        if (S.phase === 'game_over') { clearInterval(clockInterval); clockInterval = null; return; }
        const cc = currentColor();
        S.playerTimes[cc]--;

        // 連線對局的逾時由伺服器代為結算，前端只負責顯示倒數，避免雙方各自代打造成不同步
        if (isOnline) {
            if (S.playerTimes[cc] < 0) S.playerTimes[cc] = 0;
            return;
        }
        if (S.playerTimes[cc] === 0) {
            systemMsg(`⏳ ${getDisplayName(cc)}${suffixOf(cc)} 時間耗盡！系統已代為執行。`);
            executeAILogic(cc);
        }
    }, 1000);
}

export function resetCurrentPlayerTimer() {
    if (S.phase === 'game_over') return;
    S.playerTimes[currentColor()] = TURN_TIME_LIMIT;
}

// 收到伺服器狀態時：時鐘若因上一局結束而停掉就重新啟動
export function ensureClock() {
    if (!clockInterval) startClock();
}

export function checkMyTurn(cc) {
    if (isOnline) {
        if (S.spectator) { showToast('觀戰中，不能操作棋盤喔！'); return false; }
        if (S.myOnlineColor === null) { showToast('尚未獲取陣營分配，請稍候...'); return false; }
        if (cc !== S.myOnlineColor) { showToast('還沒輪到你喔！請等待對手下棋。'); return false; }
    }
    return true;
}

export function handleCellClick(r, c) {
    if (S.phase === 'game_over' || S.isProcessing) return;
    const cc = currentColor();
    if (isVsAI && cc === aiColor) return;
    if (!checkMyTurn(cc)) return;

    let actionMade = false;
    if (S.phase === 'placement') {
        if (getPieceIndexAt(r, c) !== -1) return;
        S.pieces.push(newPiece(cc, r, c));
        S.turnIndex++;
        if (S.turnIndex >= S.placementQueue.length) { S.phase = 'movement'; S.turnIndex = 0; }
        resetCurrentPlayerTimer();
        actionMade = true;
    } else if (S.phase === 'movement') {
        const clicked = getPieceIndexAt(r, c);
        if (S.selectedPieceIndex === -1) {
            if (clicked !== -1 && S.pieces[clicked].color === cc) {
                S.selectedPieceIndex = clicked; S.stepsTaken = 0; actionMade = true;
            }
        } else if (S.stepsTaken === 0 && clicked !== -1 && S.pieces[clicked].color === cc && clicked !== S.selectedPieceIndex) {
            S.selectedPieceIndex = clicked; actionMade = true;
        } else {
            const p = S.pieces[S.selectedPieceIndex];
            const isValid = movesForPiece(p).some(m => m.r === r && m.c === c);
            if (isValid) {
                if (p.r === r && p.c === c) {
                    S.movedPieceIndex = S.selectedPieceIndex; S.selectedPieceIndex = -1; S.stepsTaken = 0; S.phase = 'wall_building';
                } else {
                    if (S.stepsTaken === 0) S.moveDir = [Math.sign(r - p.r), Math.sign(c - p.c)];
                    p.r = r; p.c = c; S.stepsTaken++;
                    if (S.stepsTaken >= 2) {
                        S.movedPieceIndex = S.selectedPieceIndex; S.selectedPieceIndex = -1; S.stepsTaken = 0; S.phase = 'wall_building';
                    }
                }
                actionMade = true;
            } else if (S.stepsTaken === 0) {
                S.selectedPieceIndex = -1; actionMade = true;
            }
        }
    }

    if (actionMade) {
        saveHistoryStep();
        broadcastGameState();
        if (!isOnline) checkAITurn();
    }
}

export function handleWallClick(r, c) {
    if (S.phase === 'game_over' || S.isProcessing) return;
    const cc = currentColor();
    if (isVsAI && cc === aiColor) return;
    if (!checkMyTurn(cc)) return;

    const k = key(r, c);
    if (S.phase === 'wall_building') {
        const mp = S.pieces[S.movedPieceIndex];
        const isValid = getValidWalls(mp.r, mp.c).some(w => w.r === r && w.c === c);
        if (isValid && !S.walls.has(k)) { S.walls.set(k, cc); endTurn(); }
    } else if (S.phase === 'wall_breaking' && S.walls.has(k)) {
        if (breakableWalls(cc).has(k)) {
            S.walls.delete(k);
            S.playersInfo[cc].hasBreaker = false;
            S.phase = 'movement';
            autoCheckEndGame(false);
            saveHistoryStep();
            broadcastGameState();
        } else showToast(S.rules === 2 ? '只能拆除你棋子旁邊的牆壁！' : '只能拆除你自己建立的牆壁！');
    }
}

export function toggleWallBreaker() {
    if (S.isProcessing) return;
    const cc = S.movementOrder[S.turnIndex];
    if (!checkMyTurn(cc)) return;

    if (S.phase === 'wall_breaking') {          // 再按一次取消
        S.phase = 'movement';
        broadcastGameState();
        return;
    }
    if (S.phase === 'movement' && S.stepsTaken === 0) {
        if (!breakableWalls(cc).size) return showToast(S.rules === 2 ? '你的棋子旁邊目前沒有牆壁可以拆！' : '場上目前沒有你建立的牆壁可供拆除！');
        S.phase = 'wall_breaking'; S.selectedPieceIndex = -1;
        broadcastGameState();
    }
}

export function endTurn() {
    S.movedPieceIndex = -1; S.selectedPieceIndex = -1; S.stepsTaken = 0; S.phase = 'movement';
    S.turnIndex = (S.turnIndex + 1) % S.movementOrder.length;
    resetCurrentPlayerTimer();
    saveHistoryStep();
    autoCheckEndGame(false);
    broadcastGameState();
    if (!isOnline) checkAITurn();
}

export function autoCheckEndGame(forceCalculate = false) {
    if (S.phase === 'placement' && !forceCalculate) return;
    const check = Rules.checkGameOver(S, S.activeColors, S.playersInfo);
    const { scores } = check;
    S.territories = check.territories;
    if (!forceCalculate && !check.over) return;

    clearInterval(clockInterval); clockInterval = null;
    S.phase = 'game_over'; S.isProcessing = false;
    // 同一局只結算一次：伺服器之後再送來同一個結束盤面（重連、重新整理）時，不再重複公告與存檔
    if (finishedGameId && finishedGameId === S.gameId && S.result) return;
    finishedGameId = S.gameId;
    const reason = forceCalculate ? '因有玩家單步思考超時而強制提前結算'
        : (check.reason === 'stalemate' ? '所有玩家皆無法再進行合法操作（僵局）' : '所有陣營已被完全封閉切割');

    const sorted = [...S.activeColors].sort((a, b) => scores[b] - scores[a]);
    const ranking = sorted.map((c, i) => ({ color: c, pos: i + 1, score: scores[c], name: getDisplayName(c) + suffixOf(c) }));
    const scoreText = ranking.map(r => `第 ${r.pos} 名： ${colorMap[r.color].icon} ${r.name} 領土：${r.score} 格`).join('\n');
    const maxScore = scores[sorted[0]];
    const winners = sorted.filter(c => scores[c] === maxScore).map(c => getDisplayName(c) + (isMe(c) ? '(你)' : ''));
    const details = sorted.map(c => `${colorMap[c].text[0]}${isMe(c) ? '(你)' : ''}:${scores[c]}`);

    const historyRecord = {
        date: new Date().toLocaleString('zh-TW'),
        winner: winners.join(' & '),
        winScore: maxScore,
        details: details.join(' | '),
        game_id: S.gameId,          // 伺服器用（玩家, game_id）去重，同一局每人只留一筆
        replayData: JSON.stringify(moveHistory)
    };
    const uniqueKey = historyRecord.winScore + '_' + historyRecord.details.replace(/\s+/g, '');
    if (!S.spectator) try {
        const localReplays = JSON.parse(localStorage.getItem('wallGoReplays') || '{}');
        localReplays[uniqueKey] = historyRecord.replayData;
        localStorage.setItem('wallGoReplays', JSON.stringify(localReplays));
    } catch (e) { console.error('本地儲存空間不足', e); }

    if (session && !S.spectator) {
        historyRecord.user_id = session.id;
        fetch(`${API_URL}/api/save_history`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(historyRecord)
        }).then(res => res.json()).catch(err => console.error('戰績上傳失敗', err));
    }

    systemMsg(`🏆 遊戲結束！\n${reason}\n\n${scoreText}`);
    S.result = { reason, ranking };
    setTimeout(() => { S.showResult = true; }, 150);
}
