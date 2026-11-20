// ═══════════════════════════════════════════════════════════════
//  Wall Go 棋規（純函式，不碰畫面、不連網路）
//
//  對局頁、測試都用這一份；伺服器的 Python 版（app.py）必須通過
//  tests/rule_cases.json 裡同一批案例，兩邊才不會各說各話。
//
//  盤面座標：13×13 格，偶數 (r, c) 是棋格，一奇一偶是牆位，奇奇是交叉點。
//  state 需要的欄位：
//    pieces      [{ color, r, c, shape? }]   shape 只有規則 2 才有：'circle' | 'square'
//    walls       Map<"r,c", color>
//    rules       1 | 2
//    stepsTaken  這回合已走幾步（0 / 1）
//    moveDir     規則 2 方形棋第一步的方向 [dr, dc]
// ═══════════════════════════════════════════════════════════════

export const BOARD_SIZE = 13;
export const ALL_COLORS = ['red', 'blue', 'yellow', 'green'];
const DIRS = [[-1, 0], [1, 0], [0, -1], [0, 1]];

export const key = (r, c) => `${r},${c}`;

export function pieceIndexAt(state, r, c) {
    return state.pieces.findIndex(p => p.r === r && p.c === c);
}

export function hasWallBetween(state, r1, c1, r2, c2) {
    if (r1 === r2 && c1 === c2) return false;
    return state.walls.has(key((r1 + r2) / 2, (c1 + c2) / 2));
}

/** 從 (r, c) 走「一步」能到的棋格（含原地），不越子、不穿牆。 */
export function validMoves(state, startR, startC) {
    const out = [];
    for (let r = 0; r < BOARD_SIZE; r += 2) {
        for (let c = 0; c < BOARD_SIZE; c += 2) {
            const dr = Math.abs(startR - r), dc = Math.abs(startC - c);
            if ((dr === 2 && dc === 0) || (dr === 0 && dc === 2) || (dr === 0 && dc === 0)) {
                if (pieceIndexAt(state, r, c) === -1 || (r === startR && c === startC)) {
                    if (!hasWallBetween(state, startR, startC, r, c)) out.push({ r, c });
                }
            }
        }
    }
    return out;
}

/** 棋子停在 (r, c) 時，四周還能蓋牆的位置。 */
export function validWalls(state, pR, pC) {
    const out = [];
    for (const [dr, dc] of DIRS) {
        const wr = pR + dr, wc = pC + dc;
        if (wr >= 0 && wr < BOARD_SIZE && wc >= 0 && wc < BOARD_SIZE && !state.walls.has(key(wr, wc))) {
            out.push({ r: wr, c: wc });
        }
    }
    return out;
}

// ── 規則 2 ──

/** 規則 2：每人先放圓形、再放方形；規則 1 回傳 undefined（沒有形狀）。 */
export function nextShape(state, color) {
    if (state.rules !== 2) return undefined;
    return state.pieces.some(p => p.color === color && p.shape === 'circle') ? 'square' : 'circle';
}

export function newPiece(state, color, r, c) {
    const shape = nextShape(state, color);
    return shape ? { color, r, c, shape } : { color, r, c };
}

/** 選中的棋子這一步能去哪：規則 2 方形棋第二步只能沿第一步方向（或停在原地結束）。 */
export function movesForPiece(state, p) {
    const moves = validMoves(state, p.r, p.c);
    if (state.rules !== 2 || p.shape !== 'square' || state.stepsTaken !== 1 || !state.moveDir) return moves;
    const [dr, dc] = state.moveDir;
    return moves.filter(m => (m.r === p.r && m.c === p.c) || (m.r === p.r + 2 * dr && m.c === p.c + 2 * dc));
}

/** 可以拆的牆：規則 1 是自己蓋的牆；規則 2 是自己棋子四周的牆（不論誰蓋的）。 */
export function breakableWalls(state, color) {
    const out = new Set();
    if (state.rules !== 2) {
        state.walls.forEach((v, k) => { if (v === color) out.add(k); });
        return out;
    }
    state.pieces.forEach(p => {
        if (p.color !== color) return;
        for (const [dr, dc] of DIRS) {
            const k = key(p.r + dr, p.c + dc);
            if (state.walls.has(k)) out.add(k);
        }
    });
    return out;
}

// ── 計分與結束 ──

/**
 * 把盤面切成被牆隔開的區域：只有一種顏色的區域算那個顏色的領地。
 * 回傳 { scores: {color: 格數}, territories: Map<"r,c", color>, hasMixedTerritory }
 */
export function scoreBoard(state, activeColors) {
    const scores = {};
    activeColors.forEach(c => { scores[c] = 0; });
    const territories = new Map();
    const visited = new Set();
    let hasMixedTerritory = false;

    for (let r = 0; r < BOARD_SIZE; r += 2) {
        for (let c = 0; c < BOARD_SIZE; c += 2) {
            if (visited.has(key(r, c))) continue;
            const queue = [{ r, c }];
            visited.add(key(r, c));
            const colorsInRegion = new Set();
            const regionCells = [];
            while (queue.length > 0) {
                const cur = queue.shift();
                regionCells.push(cur);
                const pIdx = pieceIndexAt(state, cur.r, cur.c);
                if (pIdx !== -1) colorsInRegion.add(state.pieces[pIdx].color);
                for (const [dr, dc] of DIRS) {
                    const nr = cur.r + dr * 2, nc = cur.c + dc * 2;
                    if (nr >= 0 && nr < BOARD_SIZE && nc >= 0 && nc < BOARD_SIZE
                        && !state.walls.has(key(cur.r + dr, cur.c + dc)) && !visited.has(key(nr, nc))) {
                        visited.add(key(nr, nc));
                        queue.push({ r: nr, c: nc });
                    }
                }
            }
            if (colorsInRegion.size > 1) hasMixedTerritory = true;
            else if (colorsInRegion.size === 1) {
                const color = [...colorsInRegion][0];
                if (color in scores) scores[color] += regionCells.length;
                regionCells.forEach(cell => territories.set(key(cell.r, cell.c), color));
            }
        }
    }
    return { scores, territories, hasMixedTerritory };
}

/** 是否還有任何玩家能合法行動（能破牆，或有棋子走完還能蓋牆）。 */
export function anyPlayerCanMove(state, activeColors, playersInfo) {
    for (const color of activeColors) {
        if (playersInfo[color] && playersInfo[color].hasBreaker && breakableWalls(state, color).size) return true;
        for (const p of state.pieces.filter(p => p.color === color)) {
            for (const m of validMoves(state, p.r, p.c)) {
                if (validWalls(state, m.r, m.c).length > 0) return true;
            }
        }
    }
    return false;
}

/**
 * 判斷對局是否結束（放置期不判斷）。
 * 回傳 { over, reason: 'sealed' | 'stalemate' | null, scores, territories }
 */
export function checkGameOver(state, activeColors, playersInfo) {
    const { scores, territories, hasMixedTerritory } = scoreBoard(state, activeColors);
    if (!hasMixedTerritory) return { over: true, reason: 'sealed', scores, territories };
    if (!anyPlayerCanMove(state, activeColors, playersInfo)) return { over: true, reason: 'stalemate', scores, territories };
    return { over: false, reason: null, scores, territories };
}

// ── 給 AI 用的盤面評分 ──

/** 分數越高對 forColor 越有利：自己機動性高、對手機動性低、棋子靠中央。 */
export function evaluateBoard(state, forColor) {
    let score = 0, myMobility = 0, oppMobility = 0;
    state.pieces.forEach(p => {
        const movesCount = validMoves(state, p.r, p.c).length;
        if (p.color === forColor) {
            myMobility += movesCount;
            score -= (Math.abs(p.r - 6) + Math.abs(p.c - 6)) * 0.5;
        } else oppMobility += movesCount;
    });
    score += myMobility * 2.5 - oppMobility;
    if (myMobility === 0) score -= 10000;
    return score;
}
