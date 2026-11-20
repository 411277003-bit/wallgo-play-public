// 連線對局：socket 連線、斷線重連重新入房、狀態同步、觀戰名單
import '../config.js';
import { roomCode, isOnline, wantSpectate, session, S, plain, key } from './state.js';
import { appendChatMessage } from './chat.js';
import { saveHistoryStep, ensureClock, autoCheckEndGame } from './flow.js';
import { voiceOnJoined, onVoiceSignal } from './voice.js';
const { API_URL } = window.WALLGO_CONFIG;

export let socket = null;
let lastVersion = 0;   // 伺服器狀態版本，比這個舊的 update_board 一律丟掉

export function broadcastGameState() {
    if (!isOnline) return;
    socket.emit('game_action', {
        room_code: roomCode,
        pieces: plain(S.pieces),
        walls: Array.from(S.walls.entries()),
        territories: Array.from(S.territories.entries()),
        phase: S.phase,
        turnIndex: S.turnIndex,
        movedPieceIndex: S.movedPieceIndex,
        selectedPieceIndex: S.selectedPieceIndex,
        stepsTaken: S.stepsTaken,
        moveDir: S.moveDir,
        rules: S.rules,
        playersInfo: plain(S.playersInfo),
        playerTimes: plain(S.playerTimes),
        activeColors: plain(S.activeColors),
        placementQueue: plain(S.placementQueue),
        movementOrder: plain(S.movementOrder),
        gameId: S.gameId
    }, (ack) => { if (ack && ack.version > lastVersion) lastVersion = ack.version; });
}

export function applyServerState(data) {
    if (!data) return;
    if (typeof data.version === 'number') {
        if (data.version <= lastVersion) return;   // 晚到的舊狀態，忽略
        lastVersion = data.version;
    }
    if (Array.isArray(data.activeColors) && data.activeColors.length) {
        S.activeColors = data.activeColors;
        S.placementQueue = data.placementQueue || S.placementQueue;
        S.movementOrder = data.movementOrder || S.movementOrder;
    }
    S.pieces = data.pieces || [];
    // 伺服器回傳的牆是 [{r, c, color}]，前端用的是 [["r,c", color]]，兩種都接受
    S.walls = new Map((data.walls || []).map(w => Array.isArray(w) ? w : [key(w.r, w.c), w.color]));
    S.territories = new Map(data.territories || []);
    S.phase = data.phase;
    S.turnIndex = data.turnIndex;
    S.movedPieceIndex = data.movedPieceIndex;
    S.selectedPieceIndex = data.selectedPieceIndex;
    S.stepsTaken = data.stepsTaken;
    S.moveDir = data.moveDir || null;
    if (data.gameId) S.gameId = data.gameId;
    if (data.rules === 1 || data.rules === 2) S.rules = data.rules;
    if (data.playersInfo) S.playersInfo = data.playersInfo;
    if (data.playerTimes) S.playerTimes = data.playerTimes;
    // 對方按了重新開始：本機時鐘若因上一局結束而停掉，要重新啟動
    if (S.phase !== 'game_over') {
        if (S.phase === 'placement' && S.pieces.length === 0) { S.result = null; S.showResult = false; }
        ensureClock();
    }
    saveHistoryStep();
    autoCheckEndGame(false);
}

// ── 連線 ──
export function initOnline() {
    if (!isOnline) return;
    socket = io(API_URL, { reconnectionDelayMax: 3000 });

    // 每次連上（包含斷線重連、伺服器重啟後）都重新入房，否則重連後的 socket 不在房間裡，
    // 對手的棋步就再也收不到
    socket.on('connect', () => {
        socket.emit('join_game_room', {
            room_code: roomCode, user_id: session && session.id,
            user_name: session ? session.name : '訪客', spectate: wantSpectate
        });
    });

    socket.on('init_game', (data) => {
        if (data.my_color) S.myOnlineColor = data.my_color;
        if (data.spectator && !S.myOnlineColor) S.spectator = true;
        if (data.room_players && Object.keys(data.room_players).length) S.colorToName = data.room_players;
        lastVersion = 0;
        if (data.initial_state) applyServerState(data.initial_state);
        else if (S.myOnlineColor && (S.pieces.length || S.myOnlineColor === 'red')) {
            broadcastGameState();   // 伺服器重啟把房間弄丟了：用本機狀態補回去
        }
        voiceOnJoined();
    });

    socket.on('update_board', applyServerState);
    socket.on('spectators_updated', (data) => { S.spectators = (data && data.names) || []; });

    // 伺服器是計時的權威，每秒校正一次剩餘秒數
    socket.on('sync_time', (data) => {
        if (data && data.playerTimes) S.playerTimes = data.playerTimes;
    });

    socket.on('receive_chat', (data) => {
        if (typeof data.message !== 'string' || data.message.startsWith('[SYS_PEER_ID]:')) return;  // 舊版語音訊號
        appendChatMessage(data.user_name, data.color, data.message);
    });

    socket.on('voice_signal', onVoiceSignal);
}
