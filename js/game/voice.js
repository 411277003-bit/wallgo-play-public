// 語音
import { RTC_CONFIG } from '../config.js';
import { roomCode, myName, S, showToast } from './state.js';
import { systemMsg } from './chat.js';
import { socket } from './online.js';
// ── 語音（原生 WebRTC，信令走我們自己的 socket.io）──
// 以前用 PeerJS 的公用伺服器配對，那台常常連不上，而且要雙方都開麥才聽得到。
// 現在：開麥的人對房內每個人各建一條「單向送出」連線；沒開麥的人（包括觀戰者）也聽得到。
// 雙方都開麥時就是兩條方向相反的連線，不會互撥打架。
export let localStream = null;
export const outPCs = new Map();   // 對方 sid → 我送聲音給他的連線
export const inPCs = new Map();    // 對方 sid → 他送聲音給我的連線
export const talkerNames = new Map();
export const blockedAudio = new Set();

export function vsend(type, data, to) {
    if (socket) socket.emit('voice_signal', { room_code: roomCode, type, data: data || null, to: to || null });
}
export function voiceOnJoined() {
    vsend('hello');                                                    // 讓正在講話的人來接我
    if (localStream) vsend('talk-start', { name: myName || '玩家' });  // 自己重連：重新通知大家
}
export function newPC(peer, dir) {
    const pc = new RTCPeerConnection(RTC_CONFIG);
    pc._pending = [];
    pc.onicecandidate = (e) => { if (e.candidate) vsend('ice', { dir, c: e.candidate.toJSON() }, peer); };
    pc.onconnectionstatechange = () => {
        if (pc.connectionState === 'failed') {
            console.warn('語音連線失敗', peer, dir);
            if (dir === 'in') systemMsg('⚠️ 語音連不上（網路環境可能擋住點對點連線），請對方重開麥克風試試。');
            closePC(dir === 'out' ? outPCs : inPCs, peer);
        }
    };
    return pc;
}
export async function flushIce(pc) {
    for (const c of pc._pending.splice(0)) await pc.addIceCandidate(c).catch(() => {});
}
export function closePC(map, peer) {
    const pc = map.get(peer);
    if (pc) { try { pc.close(); } catch (e) {} map.delete(peer); }
    if (map === inPCs) {
        const a = document.getElementById(`audio-${peer}`);
        if (a) { blockedAudio.delete(a); a.remove(); }
    }
}
export async function offerTo(peer) {
    if (!localStream || !peer || peer === socket.id) return;
    closePC(outPCs, peer);
    const pc = newPC(peer, 'out');
    outPCs.set(peer, pc);
    localStream.getTracks().forEach(t => pc.addTrack(t, localStream));
    await pc.setLocalDescription(await pc.createOffer());
    vsend('offer', { sdp: pc.localDescription.toJSON(), name: myName || '玩家' }, peer);
}
export async function acceptOffer(peer, data) {
    closePC(inPCs, peer);
    const pc = newPC(peer, 'in');
    inPCs.set(peer, pc);
    if (data.name) talkerNames.set(peer, data.name);
    pc.ontrack = (e) => playRemote(peer, e.streams[0] || new MediaStream([e.track]));
    await pc.setRemoteDescription(data.sdp);
    await flushIce(pc);
    await pc.setLocalDescription(await pc.createAnswer());
    vsend('answer', { sdp: pc.localDescription.toJSON() }, peer);
}
export function playRemote(peer, stream) {
    let audio = document.getElementById(`audio-${peer}`);
    if (!audio) {
        audio = document.createElement('audio');
        audio.id = `audio-${peer}`;
        audio.autoplay = true;
        audio.setAttribute('playsinline', '');
        document.getElementById('audio-container').appendChild(audio);
        systemMsg(`🔊 正在收聽 ${talkerNames.get(peer) || '對手'} 的語音`);
    }
    audio.srcObject = stream;
    // 瀏覽器規定使用者還沒點過頁面前不能自動出聲，被擋就等下一次點擊再播
    audio.play().catch(() => {
        blockedAudio.add(audio);
        showToast('🔊 有人開了語音，點一下畫面就能聽到');
    });
}
document.addEventListener('pointerdown', () => {
    blockedAudio.forEach(a => a.play().catch(() => {}));
    blockedAudio.clear();
});

export async function onVoiceSignal(msg) {
    const { from, type, data } = msg || {};
    if (!from || from === socket.id) return;
    try {
        switch (type) {
            case 'hello':
            case 'listen':
                if (localStream) await offerTo(from);
                break;
            case 'talk-start':
                if (data && data.name) talkerNames.set(from, data.name);
                vsend('listen', null, from);   // 不管自己有沒有開麥都要收聽
                break;
            case 'offer':
                await acceptOffer(from, data);
                break;
            case 'answer': {
                const pc = outPCs.get(from);
                if (pc && pc.signalingState === 'have-local-offer') {
                    await pc.setRemoteDescription(data.sdp);
                    await flushIce(pc);
                }
                break;
            }
            case 'ice': {
                // 對方是送聲音那端（out）→ 套在我的接收連線上，反之亦然
                const pc = (data.dir === 'out' ? inPCs : outPCs).get(from);
                if (!pc) break;
                if (pc.remoteDescription) await pc.addIceCandidate(data.c).catch(() => {});
                else pc._pending.push(data.c);
                break;
            }
            case 'talk-stop':
                closePC(inPCs, from);
                break;
            case 'bye':
                closePC(inPCs, from);
                closePC(outPCs, from);
                break;
        }
    } catch (err) {
        console.error('voice signal error', type, err);
    }
}

export async function toggleMic() {
    if (S.spectator) return;
    if (!S.micOn) {
        if (window.location.protocol === 'file:') {
            showToast('麥克風無法在本地檔案 (file://) 使用，請用 Live Server 或 https。');
            return;
        }
        if (!navigator.mediaDevices || !window.RTCPeerConnection) {
            showToast('這個瀏覽器不支援語音，請改用 Chrome / Edge / Safari。');
            return;
        }
        try {
            localStream = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }, video: false
            });
        } catch (err) {
            console.error('Mic error:', err);
            showToast(err && err.name === 'NotAllowedError'
                ? '麥克風權限被拒絕了，請點網址列左邊的鎖頭開啟。'
                : '找不到可用的麥克風！');
            return;
        }
        S.micOn = true;
        vsend('talk-start', { name: myName || '玩家' });
        systemMsg('🎤 麥克風已開啟，房內所有人都聽得到你。');
    } else {
        [...outPCs.keys()].forEach(peer => closePC(outPCs, peer));
        if (localStream) { localStream.getTracks().forEach(t => t.stop()); localStream = null; }
        S.micOn = false;
        vsend('talk-stop');
        systemMsg('🔇 麥克風已關閉。');
    }
}
