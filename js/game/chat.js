// 聊天室：訊息列表、送出、系統訊息、@標記
import { roomCode, isOnline, session, myName, S } from './state.js';
import { socket } from './online.js';
const { computed, nextTick } = Vue;

let chatSeq = 0;

// ── 聊天 ──
export function appendChatMessage(name, color, text) {
    S.chat.push({ id: ++chatSeq, name, color, text });
    if (!S.chatOpen && name !== myName && name !== '系統') S.unread = true;
    nextTick(() => {
        const box = document.querySelector('.chat-messages');
        if (box) box.scrollTop = box.scrollHeight;
    });
}
export function emitChat(message, name, color) {
    if (isOnline) socket.emit('send_chat', { room_code: roomCode, user_name: name, color, message });
}
export function sendMsg(msg) {
    const name = session ? session.name : '玩家';
    const color = S.myOnlineColor || (S.spectator ? 'spectator' : 'red');
    appendChatMessage(name, color, msg);
    emitChat(msg, name, color);
}
export function sendChat() {
    const msg = S.chatInput.trim();
    if (!msg) return;
    sendMsg(msg);
    S.chatInput = '';
}
export function systemMsg(text, broadcast) {
    appendChatMessage('系統', 'yellow', text);
    if (broadcast) emitChat(text, '系統', 'yellow');
}

// ── @標記 ──
export const mentionOptions = computed(() => {
    const val = S.chatInput;
    const lastAt = val.lastIndexOf('@');
    if (lastAt === -1 || val.includes(' ', lastAt)) return [];
    const q = val.substring(lastAt + 1).toLowerCase();
    return Object.values(S.colorToName).filter(n => n.toLowerCase().includes(q));
});
export function pickMention(name) {
    const val = S.chatInput;
    S.chatInput = val.substring(0, val.lastIndexOf('@')) + `@${name} `;
    nextTick(() => document.querySelector('.chat-input input').focus());
}
// 把訊息切成一般文字與「@我」兩種片段；全部以文字輸出，不經 innerHTML
export function splitMention(text) {
    if (!myName) return [{ text }];
    const tag = '@' + myName;
    const parts = String(text).split(tag);
    const out = [];
    parts.forEach((p, i) => {
        if (i > 0) out.push({ text: tag, mention: true });
        if (p) out.push({ text: p });
    });
    return out;
}
