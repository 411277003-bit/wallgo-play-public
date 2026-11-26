// 封包紀錄器：記下連線對局裡每一個封包的往返時間、大小、伺服器有沒有接受、斷線重連花多久。
//
// 打開方式（只在連線對局有用）：
//   - 網址後面加 &netlog=1，或在對局頁按 Ctrl + Shift + L，右下角會出現統計面板
//   - 主控台輸入 wallgoNetLog.summary() 看統計、wallgoNetLog.downloadCSV() 下載每一筆紀錄
//
// 記錄的東西（全部只存在這個分頁的記憶體，不會上傳）：
//   send      送出 game_action：JSON 大小、當時的階段
//   ack       收到伺服器確認：往返時間（RTT）、接受或拒絕（拒絕原因）
//   recv      收到對手的 update_board：JSON 大小
//   tick      伺服器每秒一次的 sync_time：跟上一次間隔幾毫秒（正常約 1000 ms，越穩定越好）
//   disconnect／reconnect：斷線原因、斷了多久才重新入房並拿到盤面

const startedAt = performance.now();
const rows = [];          // 每一筆紀錄
const pending = new Map(); // 送出還沒收到 ack 的：id → { t, bytes, phase }
let seq = 0, lastTick = null, downAt = null;
const enc = new TextEncoder();
const sizeOf = (obj) => { try { return enc.encode(JSON.stringify(obj)).length; } catch (e) { return 0; } };
const now = () => performance.now();
const clock = () => new Date().toLocaleTimeString('zh-TW', { hour12: false });

function add(row) {
    rows.push({ n: rows.length + 1, clock: clock(), t_ms: Math.round(now() - startedAt), ...row });
    if (panel && panel.style.display !== 'none') render();
}

// ── 給 online.js 呼叫的記錄點 ──
export const netlog = {
    sent(payload) {
        const id = ++seq;
        const bytes = sizeOf(payload);
        pending.set(id, { t: now(), bytes, phase: payload.phase });
        add({ type: 'send', phase: payload.phase, bytes });
        return id;
    },
    ack(id, ack) {
        const p = pending.get(id);
        if (!p) return;
        pending.delete(id);
        add({ type: 'ack', phase: p.phase, bytes: sizeOf(ack), rtt_ms: +(now() - p.t).toFixed(1),
              result: ack && !ack.error ? 'accepted' : 'rejected', detail: (ack && ack.error) || '' });
    },
    recv(name, data) {
        add({ type: 'recv', phase: data && data.phase, bytes: sizeOf(data), detail: name });
    },
    tick() {
        const t = now();
        if (lastTick !== null) add({ type: 'tick', interval_ms: +(t - lastTick).toFixed(1) });
        lastTick = t;
    },
    disconnect(reason) {
        downAt = now();
        lastTick = null;   // 斷線期間的空檔不算進計時間隔
        add({ type: 'disconnect', detail: String(reason || '') });
    },
    rejoined() {
        // 收到 init_game（已重新入房、拿到盤面）才算恢復
        if (downAt === null) return;
        add({ type: 'reconnect', downtime_ms: Math.round(now() - downAt) });
        downAt = null;
    },
};

// ── 統計 ──
const pct = (arr, p) => {
    if (!arr.length) return null;
    const s = [...arr].sort((a, b) => a - b);
    return s[Math.min(s.length - 1, Math.floor(s.length * p / 100))];
};
const mean = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null;
const stdev = (arr) => {
    const m = mean(arr);
    return arr.length > 1 ? Math.sqrt(arr.reduce((a, b) => a + (b - m) ** 2, 0) / (arr.length - 1)) : null;
};
const r1 = (x) => x === null ? null : Math.round(x * 10) / 10;

export function summary() {
    const acks = rows.filter(r => r.type === 'ack');
    const rtt = acks.map(r => r.rtt_ms);
    const sends = rows.filter(r => r.type === 'send');
    const recvs = rows.filter(r => r.type === 'recv');
    const ticks = rows.filter(r => r.type === 'tick').map(r => r.interval_ms);
    const recon = rows.filter(r => r.type === 'reconnect').map(r => r.downtime_ms);
    return {
        紀錄秒數: Math.round((now() - startedAt) / 1000),
        送出動作: sends.length,
        收到確認: acks.length,
        伺服器拒絕: acks.filter(r => r.result === 'rejected').length,
        沒有回應: pending.size,
        往返時間_平均ms: r1(mean(rtt)), 往返時間_中位數ms: r1(pct(rtt, 50)),
        往返時間_p95ms: r1(pct(rtt, 95)), 往返時間_最大ms: r1(rtt.length ? Math.max(...rtt) : null),
        往返時間_標準差ms: r1(stdev(rtt)),
        送出封包_平均bytes: r1(mean(sends.map(r => r.bytes))), 送出封包_最大bytes: sends.length ? Math.max(...sends.map(r => r.bytes)) : null,
        收到盤面更新: recvs.length, 收到封包_平均bytes: r1(mean(recvs.map(r => r.bytes))),
        計時同步次數: ticks.length, 計時間隔_平均ms: r1(mean(ticks)), 計時間隔_標準差ms: r1(stdev(ticks)),
        計時間隔_超過1500ms: ticks.filter(x => x > 1500).length,
        斷線次數: rows.filter(r => r.type === 'disconnect').length,
        重連平均ms: r1(mean(recon)), 重連最久ms: recon.length ? Math.max(...recon) : null,
    };
}

export function downloadCSV() {
    const cols = ['n', 'clock', 't_ms', 'type', 'phase', 'bytes', 'rtt_ms', 'result', 'detail', 'interval_ms', 'downtime_ms'];
    const esc = (v) => v === undefined || v === null ? '' : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v);
    const sum = Object.entries(summary()).map(([k, v]) => `# ${k},${v ?? ''}`);
    const csv = '﻿' + [...sum, cols.join(','), ...rows.map(r => cols.map(c => esc(r[c])).join(','))].join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    a.download = `wallgo-netlog-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export function clear() {
    rows.length = 0; pending.clear(); lastTick = null;
    if (panel) render();
}

// ── 右下角的統計面板（純 DOM，不動到 Vue 的畫面） ──
let panel = null, body = null;
function render() {
    const s = summary();
    const line = (k, v, unit = '') => `<div style="display:flex;justify-content:space-between;gap:12px"><span>${k}</span><b>${v ?? '–'}${v === null || v === undefined ? '' : unit}</b></div>`;
    body.innerHTML = [
        line('紀錄時間', s.紀錄秒數, ' 秒'),
        line('送出動作 / 拒絕', `${s.送出動作} / ${s.伺服器拒絕}`),
        line('往返 平均', s.往返時間_平均ms, ' ms'),
        line('往返 中位數', s.往返時間_中位數ms, ' ms'),
        line('往返 p95', s.往返時間_p95ms, ' ms'),
        line('往返 最大', s.往返時間_最大ms, ' ms'),
        line('送出封包平均', s.送出封包_平均bytes, ' B'),
        line('收到更新 / 平均', s.收到盤面更新 ? `${s.收到盤面更新} / ${s.收到封包_平均bytes}` : null, ' B'),
        line('計時間隔 平均', s.計時間隔_平均ms, ' ms'),
        line('計時間隔 標準差', s.計時間隔_標準差ms, ' ms'),
        line('斷線 / 重連平均', s.斷線次數 ? `${s.斷線次數} / ${s.重連平均ms ?? '–'}` : 0, s.重連平均ms ? ' ms' : ''),
    ].join('');
}
export function togglePanel(force) {
    if (!panel) {
        panel = document.createElement('div');
        panel.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:9999;width:240px;padding:10px 12px;' +
            'background:rgba(20,20,24,.92);color:#eee;font:12px/1.6 system-ui,sans-serif;border-radius:10px;' +
            'box-shadow:0 4px 18px rgba(0,0,0,.4)';
        panel.innerHTML = '<div style="font-weight:700;margin-bottom:4px">📡 封包紀錄器</div><div></div>' +
            '<div style="display:flex;gap:6px;margin-top:8px">' +
            '<button data-a="csv" style="flex:1">下載 CSV</button><button data-a="clear">清除</button><button data-a="x">✕</button></div>';
        body = panel.children[1];
        panel.addEventListener('click', (e) => {
            const a = e.target.dataset && e.target.dataset.a;
            if (a === 'csv') downloadCSV();
            if (a === 'clear') clear();
            if (a === 'x') togglePanel(false);
        });
        document.body.appendChild(panel);
        setInterval(() => { if (panel.style.display !== 'none') render(); }, 1000);
    }
    const show = force ?? panel.style.display === 'none';
    panel.style.display = show ? 'block' : 'none';
    if (show) render();
}

if (typeof window !== 'undefined' && typeof document !== 'undefined' && document.body) {
    window.wallgoNetLog = { summary, downloadCSV, clear, show: () => togglePanel(true), rows };
    if (new URLSearchParams(location.search).get('netlog') === '1') togglePanel(true);
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.shiftKey && (e.key === 'L' || e.key === 'l')) { e.preventDefault(); togglePanel(); }
    });
}
