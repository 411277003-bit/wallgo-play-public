// 單機電腦 AI 與逾時代打（連線對局的逾時由伺服器處理）
import { boardSize, isOnline, isVsAI, aiColor, S, key, currentColor, getPieceIndexAt, getValidMoves, getValidWalls, newPiece, breakableWalls, evaluateBoard } from './state.js';
import { saveHistoryStep, resetCurrentPlayerTimer, autoCheckEndGame } from './flow.js';

export function executeAILogic(color) {
    if (S.phase === 'movement' && S.stepsTaken > 0 && S.selectedPieceIndex !== -1) {
        S.movedPieceIndex = S.selectedPieceIndex;
        S.selectedPieceIndex = -1; S.stepsTaken = 0; S.phase = 'wall_building';
    }

    if (S.phase === 'placement') {
        const emptyCells = [];
        for (let r = 0; r < boardSize; r += 2)
            for (let c = 0; c < boardSize; c += 2)
                if (getPieceIndexAt(r, c) === -1) emptyCells.push({ r, c });
        if (emptyCells.length > 0) {
            const rand = emptyCells[Math.floor(Math.random() * emptyCells.length)];
            S.pieces.push(newPiece(S.placementQueue[S.turnIndex], rand.r, rand.c));
        }
        S.turnIndex++;
        if (S.turnIndex >= S.placementQueue.length) { S.phase = 'movement'; S.turnIndex = 0; }
    } else if (S.phase === 'wall_building') {
        const mp = S.pieces[S.movedPieceIndex];
        const possibleWalls = getValidWalls(mp.r, mp.c);
        if (possibleWalls.length > 0) {
            const w = possibleWalls[Math.floor(Math.random() * possibleWalls.length)];
            S.walls.set(key(w.r, w.c), color);
        }
        S.movedPieceIndex = -1; S.selectedPieceIndex = -1; S.stepsTaken = 0; S.phase = 'movement';
        S.turnIndex = (S.turnIndex + 1) % S.movementOrder.length;
    } else {
        const myPieces = S.pieces.map((p, idx) => ({ ...p, idx })).filter(p => p.color === color);
        const isTimeoutBreak = S.phase === 'wall_breaking';
        let totalMobility = 0;
        myPieces.forEach(p => totalMobility += getValidMoves(p.r, p.c).length);

        const myWalls = [...breakableWalls(color)];
        if (S.playersInfo[color].hasBreaker && myWalls.length > 0 && (totalMobility <= 2 || isTimeoutBreak)) {
            S.walls.delete(myWalls[Math.floor(Math.random() * myWalls.length)]);
            S.playersInfo[color].hasBreaker = false;
        }

        let bestAction = null, bestScore = -Infinity;
        myPieces.forEach(p => {
            getValidMoves(p.r, p.c).forEach(m => {
                const oldR = p.r, oldC = p.c;
                p.r = m.r; p.c = m.c;
                getValidWalls(m.r, m.c).forEach(w => {
                    S.walls.set(key(w.r, w.c), color);
                    const score = evaluateBoard(color) + Math.random() * 0.1;
                    if (score > bestScore) {
                        bestScore = score;
                        bestAction = { pIdx: p.idx, mr: m.r, mc: m.c, wr: w.r, wc: w.c };
                    }
                    S.walls.delete(key(w.r, w.c));
                });
                p.r = oldR; p.c = oldC;
            });
        });

        if (bestAction) {
            S.pieces[bestAction.pIdx].r = bestAction.mr;
            S.pieces[bestAction.pIdx].c = bestAction.mc;
            S.walls.set(key(bestAction.wr, bestAction.wc), color);
        } else if (myPieces.length > 0) {
            const fb = myPieces[0];
            const wMoves = getValidWalls(fb.r, fb.c);
            if (wMoves.length > 0) S.walls.set(key(wMoves[0].r, wMoves[0].c), color);
        }

        S.movedPieceIndex = -1; S.selectedPieceIndex = -1; S.stepsTaken = 0; S.phase = 'movement';
        S.turnIndex = (S.turnIndex + 1) % S.movementOrder.length;
    }

    saveHistoryStep();
    resetCurrentPlayerTimer();
    autoCheckEndGame(false);
    checkAITurn();
}

export function checkAITurn() {
    if (S.phase === 'game_over' || isOnline) { S.isProcessing = false; return; }
    const cc = currentColor();
    if (isVsAI && cc === aiColor) {
        S.isProcessing = true;
        setTimeout(() => executeAILogic(cc), 800);
    } else S.isProcessing = false;
}
