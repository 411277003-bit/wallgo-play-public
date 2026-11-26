// 執行：node tests/lobby_xss.test.mjs   （不用安裝套件）
//
// 好友列表的 XSS 回歸測試：載入真正的 js/lobby/core.js（esc）與 js/lobby/friends.js，
// 用惡意的 ID／暱稱渲染列表，確認：
//   1. 產生的 HTML 裡沒有任何 onclick 之類的行內事件（以前 ID 會被塞進 onclick='...' 字串裡執行）
//   2. 惡意字串只會以跳脫過的文字出現
//   3. 點按鈕時，事件委派拿到的 ID 跟原本的字串一模一樣（被當成資料，不會被執行）
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

let failed = 0, total = 0;
const check = (name, ok) => { total++; if (!ok) failed++; console.log(`  ${ok ? '✓' : '✗'} ${name}`); };

// ── 假的 DOM：只做 friends.js 需要的部分 ──
const elements = {};
let clickHandler = null;
const el = (id) => elements[id] ??= {
    id, innerHTML: '', innerText: '', value: '',
    addEventListener: (type, fn) => { if (id === 'friend-list-render' && type === 'click') clickHandler = fn; },
};
const calls = [];
const sandbox = {
    document: { getElementById: el, querySelectorAll: () => [], addEventListener: () => {} },
    addEventListener: () => {}, setTimeout: () => 0, clearTimeout: () => {},
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    window: { WALLGO_CONFIG: { API_URL: '' } },
    io: () => ({ on() {}, emit() {} }),
    console,
};
vm.createContext(sandbox);
// core.js 用 const 宣告的東西（esc、currentUser…）要在同一個 script 範圍內才看得到，所以接在一起執行
const src = ['js/config.js', 'js/lobby/core.js', 'js/lobby/friends.js']
    .map(f => readFileSync(new URL(`../${f}`, import.meta.url), 'utf8')).join('\n;\n');
vm.runInContext(src + `
;globalThis.__render = renderFriendsUI;
inviteFriend = (id) => __calls.push(['invite', id]);
handleFriendReq = (id, action) => __calls.push([action, id]);`, Object.assign(sandbox, { __calls: calls }));

const evil = `#x');alert(1);//`;
const evilName = `<img src=x onerror=alert(2)>`;
const evilQuote = `"><script>alert(3)</script>`;
sandbox.__render(
    [{ id: evil, name: evilName, avatar: '<b>' }],
    [{ id: evilQuote, name: 'p', avatar: 'P' }],
    [{ id: evil, name: evilName, avatar: 'E' }],
);
const html = elements['friend-list-render'].innerHTML;

// 只看真正的標籤 <...> 裡的屬性（跳脫後的文字裡出現 onerror= 只是文字，不算）
check('HTML 標籤裡沒有任何 onclick／onerror 等行內事件屬性', !/<[a-z][^>]*\son[a-z]+\s*=/i.test(html));
check('惡意暱稱被跳脫成文字（沒有真的 <img> 標籤）', !html.includes('<img') && html.includes('&lt;img'));
check('惡意 ID 的引號被跳脫', !html.includes(`'${evil}`) && html.includes('&#39;'));
check('想跳出屬性的 "> 被跳脫', !html.includes('"><script>') && html.includes('&quot;&gt;&lt;script&gt;'));

// ── 模擬點按鈕：瀏覽器會把 data-id 的 &#39; 還原成 '，dataset 拿到的是原本的字串 ──
const unescape = (s) => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
const buttons = [...html.matchAll(/<button[^>]*data-friend-action="([a-z]+)"[^>]*data-id="([^"]*)"/g)]
    .map(m => ({ action: m[1], id: unescape(m[2]) }));
check('列表上有同意、拒絕、邀請三種按鈕', ['accept', 'reject', 'invite'].every(a => buttons.some(b => b.action === a)));
for (const b of buttons) {
    clickHandler({ target: { closest: () => ({ dataset: { id: b.id, friendAction: b.action } }) } });
}
check('點「同意」傳給 handleFriendReq 的是原本的 ID 字串（被當成資料）',
    calls.some(([a, id]) => a === 'accept' && id === evil));
check('點「邀請對戰」傳給 inviteFriend 的也是原本的字串', calls.some(([a, id]) => a === 'invite' && id === evil));
check('沒有任何程式碼被執行（只有 3 次預期中的呼叫）', calls.length === 3);

console.log(failed ? `\n共 ${total} 項，${failed} 個失敗` : `\n全部 ${total} 項通過`);
process.exit(failed ? 1 : 0);
