// train.js
import fs from 'fs';
import { WallGoGame } from './wallgo_logic.js';
import { WallGoAI } from './ai_agent.js';

// 讀取目前的最佳基因，如果沒有就預設為 1.0
let bestData;
try {
    const fileContent = fs.readFileSync('./best_weights.json', 'utf8');
    bestData = JSON.parse(fileContent).weights;
} catch (e) {
    bestData = { w_territory: 1.0, w_mobility: 1.0, w_center: 1.0 };
}

let champion = new WallGoAI(bestData.w_territory, bestData.w_mobility, bestData.w_center);
let generation = 1;

console.log("🚀 開始 AI 演化訓練...");

// 進入無限訓練迴圈
while (true) {
    let challenger = champion.mutate();
    let challengerScore = 0;
    
    console.log(`\n--- 第 ${generation} 代挑戰開始 ---`);
    
    // 先到 10 分 或 -10 分
    while (Math.abs(challengerScore) < 10) {
        let game = new WallGoGame();
        
        // 🌟 1. 隨機決定衛冕者是紅方還是藍方 (防止 AI 只會下先手或後手)
        let championIsRed = Math.random() < 0.5;
        
        // 🌟 2. 隨機產生不重複的初始座標 (範圍 0~12 之間的偶數)
        let r1 = Math.floor(Math.random() * 7) * 2;
        let c1 = Math.floor(Math.random() * 7) * 2;
        let r2, c2;
        do {
            r2 = Math.floor(Math.random() * 7) * 2;
            c2 = Math.floor(Math.random() * 7) * 2;
        } while (r1 === r2 && c1 === c2);

        game.pieces.push({ color: 'red', r: r1, c: c1 });
        game.pieces.push({ color: 'blue', r: r2, c: c2 });
        game.phase = 'movement';
        
        let turn = 'red';
        let stepCount = 0;
        
        // 遊戲主迴圈
        while (game.phase !== 'game_over' && stepCount < 200) {
            // 🌟 3. 動態決定現在是誰的回合，並呼叫對應的大腦
            let isCurrentTurnChampion = (turn === 'red') ? championIsRed : !championIsRed;
            let currentAI = isCurrentTurnChampion ? champion : challenger;
            let action = currentAI.getBestMove(game, turn);
            
            if (action) {
                // 移動棋子與建牆
                game.applyMove(action.pIdx, action.mr, action.mc, action.wr, action.wc, turn);
                // 🛑 呼叫 BFS 檢查是否有人被封死
                game.checkEndGame(); 
            } else {
                game.phase = 'game_over'; // 沒步可走
            }
            
            // 只有當遊戲還沒結束時才切換回合，確保最後停在輸家身上
            if (game.phase !== 'game_over') {
                turn = turn === 'red' ? 'blue' : 'red';
            }
            stepCount++;
        }
        
        // --- 修正後的勝負判定邏輯 ---
        // 1. 如果 BFS 有算出贏家，就用算出來的
        // 2. 如果是因為沒步可走而跳出，代表「當下回合的人 (turn)」被卡死了，所以對手贏
        let finalWinner = game.winner || (turn === 'red' ? 'blue' : 'red');
        
        // 🌟 4. 根據真實身分計分 (取代寫死的顏色計分)
        if (finalWinner !== 'Draw') {
            let challengerWon = (finalWinner === 'red' && !championIsRed) || (finalWinner === 'blue' && championIsRed);
            if (challengerWon) {
                challengerScore++; // 挑戰者贏
            } else {
                challengerScore--; // 衛冕者贏
            }
        }
    }
    
    // 結算這一代
    if (challengerScore >= 10) {
        console.log(`🎉 挑戰者篡位成功！新基因寫入硬碟...`);
        champion = challenger;
        
        // 存檔
        const output = {
            version: generation,
            weights: {
                w_territory: champion.w_territory,
                w_mobility: champion.w_mobility,
                w_center: champion.w_center
            }
        };
        fs.writeFileSync('./best_weights.json', JSON.stringify(output, null, 2));
    } else {
        console.log(`💀 挑戰者失敗，基因淘汰。`);
    }
    generation++;
}