// 執行：node tests/rules.test.mjs
// 用 tests/rule_cases.json 的盤面檢查 js/shared/rules.js，不需要安裝任何套件。
import { readFileSync } from 'node:fs';
import * as Rules from '../js/shared/rules.js';

const { cases } = JSON.parse(readFileSync(new URL('./rule_cases.json', import.meta.url), 'utf8'));
const toKeys = (list) => list.map(x => typeof x === 'string' ? x : Rules.key(x.r, x.c)).sort();
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

let failed = 0;
for (const tc of cases) {
    const state = {
        rules: tc.rules,
        pieces: tc.pieces,
        walls: new Map(tc.walls),
        stepsTaken: tc.stepsTaken ?? 0,
        moveDir: tc.moveDir ?? null
    };
    let got, want = tc.expect;
    switch (tc.check) {
        case 'movesForPiece':  got = toKeys(Rules.movesForPiece(state, state.pieces[tc.piece])); want = [...want].sort(); break;
        case 'validWalls':     got = toKeys(Rules.validWalls(state, ...tc.at)); want = [...want].sort(); break;
        case 'breakableWalls': got = toKeys([...Rules.breakableWalls(state, tc.color)]); want = [...want].sort(); break;
        case 'nextShape':      got = Rules.nextShape(state, tc.color) ?? null; break;
        case 'checkGameOver': {
            const info = Object.fromEntries(tc.colors.map(c => [c, { hasBreaker: true }]));
            const r = Rules.checkGameOver(state, tc.colors, info);
            got = { over: r.over };
            if ('reason' in want) got.reason = r.reason;
            if ('scores' in want) got.scores = r.scores;
            break;
        }
        default: throw new Error(`未知的 check：${tc.check}`);
    }
    if (same(got, want)) console.log(`  ✓ ${tc.name}`);
    else { failed++; console.log(`  ✗ ${tc.name}\n      預期 ${JSON.stringify(want)}\n      實際 ${JSON.stringify(got)}`); }
}
console.log(failed ? `\n${failed} 個失敗` : `\n全部 ${cases.length} 個通過`);
process.exit(failed ? 1 : 0);
