// 前端共用設定：後端網址、每回合秒數、語音連線用的 STUN/TURN

export const API_URL = 'https://wallgo-play.onrender.com';
export const TURN_TIME_LIMIT = 90;

// 語音（WebRTC）用來找到彼此的伺服器
export const RTC_CONFIG = {
    iceServers: [
        { urls: ['stun:stun.l.google.com:19302', 'stun:stun1.l.google.com:19302', 'stun:stun.cloudflare.com:3478'] }
        // 有 TURN 伺服器的話加在這裡（不同電信／公司網路互連時才需要）：
        // { urls: 'turn:你的網域:3478', username: '...', credential: '...' }
    ]
};
