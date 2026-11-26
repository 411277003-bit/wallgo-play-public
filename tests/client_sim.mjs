// 由 tests/test_client_parity.py 呼叫：node tests/client_sim.mjs <seed> <games> <players> <rules>
//
// 在 Node 裡載入「真正的」對局頁程式（js/game/flow.js、online.js、state.js…），把瀏覽器的東西換成假的，
// 然後隨機亂點棋盤（包含點錯地方、切換破牆模式、取消、重新開始），
// 把前端每一次送給伺服器的 game_action 內容印成一行 JSON，交給 Python 端逐一驗證。
// 目的：確認伺服器的棋步驗證跟前端實際送出的資料完全一致，不會誤擋正常玩家。

const [seed = 1, games = 5, players = 2, rules = 1] = process.argv.slice(2).map(Number);

// ── 可重現的亂數 ──
let x = seed >>> 0 || 1;
const rand = () => ((x = (x * 1664525 + 1013904223) >>> 0) / 2 ** 32);
const pick = (arr) => arr[Math.floor(rand() * arr.length)];

// ── 假的瀏覽器環境 ──
const sent = [];
const fakeSocket = { emit(name, data, cb) { if (name === 'game_action') sent.push(JSON.parse(JSON.stringify(data))); }, on() {} };
const store = {};
Object.assign(globalThis, {
    window: { location: { search: `?mode=online&room=1234&players=${players}&rules=${rules}` } },
    localStorage: { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } },
    document: { querySelector: () => null, addEventListener: () => {} },
    Vue: { reactive: (o) => o, computed: (f) => ({ get value() { return f(); } }), nextTick: (f) => f && f() },
    io: () => fakeSocket,
    fetch: async () => ({ json: async () => ({}) }),
    setInterval: () => 0, clearInterval: () => {}, setTimeout: () => 0, clearTimeout: () => {},
});
globalThis.window.WALLGO_CONFIG = undefined;

const { S } = await import('../js/game/state.js');
const flow = await import('../js/game/flow.js');
const online = await import('../js/game/online.js');
const Rules = await import('../js/shared/rules.js');
online.initOnline();

const out = [];
let lastLen = 0;
function flush(actor) {
    while (lastLen < sent.length) out.push({ actor, data: sent[lastLen++] });
}

for (let g = 0; g < games; g++) {
    // 每一局：第一位玩家按「重新開始」
    S.myOnlineColor = 'red';
    flow.resetGame(true);
    flush('red');
    for (let i = 0; i < 2000 && S.phase !== 'game_over'; i++) {
        const cc = S.phase === 'placement' ? S.placementQueue[S.turnIndex] : S.movementOrder[S.turnIndex];
        S.myOnlineColor = cc;          // 換成輪到的那位玩家在操作
        const roll = rand();
        if (S.phase === 'movement' && roll < 0.04) {
            // 破牆鈕（介面上只有還有破牆權時才按得到）
            if (S.playersInfo[cc]?.hasBreaker && S.stepsTaken === 0) flow.toggleWallBreaker();
        } else if (S.phase === 'wall_breaking') {
            if (roll < 0.2) flow.toggleWallBreaker();                     // 取消
            else {
                const ks = [...S.walls.keys()];
                if (ks.length) { const [r, c] = pick(ks).split(',').map(Number); flow.handleWallClick(r, c); }
                else flow.toggleWallBreaker();
            }
        } else if (S.phase === 'wall_building') {
            const mp = S.pieces[S.movedPieceIndex];
            const walls = Rules.validWalls(S, mp.r, mp.c);
            if (walls.length && roll < 0.9) { const w = pick(walls); flow.handleWallClick(w.r, w.c); }
            else flow.handleWallClick(2 * Math.floor(rand() * 6) + 1, 2 * Math.floor(rand() * 7));   // 亂點一道牆
        } else {
            // 放置期／移動期：大部分點合理的位置，偶爾亂點
            let r, c;
            if (S.phase === 'movement' && S.selectedPieceIndex !== -1 && roll < 0.8) {
                const p = S.pieces[S.selectedPieceIndex];
                const moves = Rules.movesForPiece(S, p);
                ({ r, c } = pick(moves));
            } else if (S.phase === 'movement' && roll < 0.85) {
                const mine = S.pieces.filter(p => p.color === cc);
                ({ r, c } = pick(mine));
            } else {
                r = 2 * Math.floor(rand() * 7); c = 2 * Math.floor(rand() * 7);
            }
            flow.handleCellClick(r, c);
        }
        flush(cc);
    }
}
process.stdout.write(out.map(o => JSON.stringify(o)).join('\n') + '\n');
process.exit(0);
