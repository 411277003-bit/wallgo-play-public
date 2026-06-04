// ai_agent.js
export class WallGoAI {
    constructor(w_territory, w_mobility, w_center) {
        this.w_territory = w_territory;
        this.w_mobility = w_mobility;
        this.w_center = w_center; // 佔領中心的權重
    }

    // 產生稍微變異的挑戰者
    mutate() {
        const rate = 0.1;
        return new WallGoAI(
            this.w_territory + (Math.random() * rate * 2 - rate),
            this.w_mobility + (Math.random() * rate * 2 - rate),
            this.w_center + (Math.random() * rate * 2 - rate)
        );
    }

    // 核心評分公式 (最新終極非線性降噪與全淨值歸一化版)
    evaluateBoard(game, aiColor) {
        let score = 0;
        
        let aiMobilityRaw = 0;
        let oppMobilityRaw = 0;
        let aiTerritory = 0;
        let oppTerritory = 0;
        let aiCenter = 0;
        let oppCenter = 0;

        // 追蹤個別棋子是否被完全卡死（2v2 雙棋子聯防機制）
        let aiTrappedPieces = 0;
        let oppTrappedPieces = 0;

        game.pieces.forEach(p => {
            // 1. 機動性計算與歸一化 (單一棋子最大包含自身格為 5 步，轉為 0 ~ 1)
            let movesCount = game.getValidMoves(p.r, p.c).length;
            let normMobility = movesCount / 5; 
            
            // 2. 🌟【中心控制拋物線降噪】(最大曼哈頓距離 12，轉為 0 ~ 1，越近越趨近 1)
            // 將線性改成二次方衰減：1 - (distance/12)^2
            // 消除 AI 在中心點附近微觀「刷分行為」的強迫症，強制壓制 w_center 暴增
            let centerDistance = Math.abs(p.r - 6) + Math.abs(p.c - 6); 
            let normCenter = 1 - Math.pow(centerDistance / 12, 2); 
            
            // 3. 🌟【領土開闊度真正啟用】(四周最大 4 個建牆位，轉為 0 ~ 1，周圍越開闊分數越高)
            // 讓 w_territory 真正進入賽局，使 AI 具備宏觀擴張領土、包圍對手的思維
            let validWalls = game.getValidWalls(p.r, p.c).length;
            let normTerritory = validWalls / 4; 

            // 分流累加我方與敵方棋子的特徵值
            if (p.color === aiColor) {
                aiMobilityRaw += normMobility;
                aiCenter += normCenter;
                aiTerritory += normTerritory;
                if (movesCount <= 1) aiTrappedPieces++; // 扣除原地踏步，若只剩 1 步或沒步算卡死
            } else {
                oppMobilityRaw += normMobility;
                oppCenter += normCenter;
                oppTerritory += normTerritory;
                if (movesCount <= 1) oppTrappedPieces++;
            }
        });

        // 4. 🌟【機動性開根號處理】(實作邊際效益遞減)
        // 消除 AI 斤斤計較微觀步數的極端執著，大幅釋放演化壓力，壓制 w_mobility 暴增
        let aiMobilityScore = Math.sqrt(aiMobilityRaw);
        let oppMobilityScore = Math.sqrt(oppMobilityRaw);

        // 5. 全面實作「我方淨值 - 敵方淨值」的對抗公式，確保各特徵量綱絕對平衡 (-1.0 ~ +1.0)
        let diffTerritory = aiTerritory - oppTerritory;
        let diffMobility = aiMobilityScore - oppMobilityScore;
        let diffCenter = aiCenter - oppCenter;

        // 🏆 核心權重算式組合
        score += (diffTerritory * this.w_territory);
        score += (diffMobility * this.w_mobility);
        score += (diffCenter * this.w_center);
        
        // 絕對邊界懲罰（2v2 無情聯防機制）
        if (aiTrappedPieces > 0) score -= (10000 * aiTrappedPieces); // 任何一隻被圍死就給予重罰
        if (oppTrappedPieces > 0) score += (8000 * oppTrappedPieces); // 成功合圍敵方任意棋子給予巨大獎勵

        return score;
    }

    // 找出最佳走法
    getBestMove(game, aiColor) {
        let bestAction = null;
        let bestScore = -Infinity;
        
        let myPieces = game.pieces.map((p, idx) => ({...p, idx})).filter(p => p.color === aiColor);

        myPieces.forEach(p => {
            let moves = game.getValidMoves(p.r, p.c);
            moves.forEach(m => {
                let oldR = p.r; let oldC = p.c;
                game.pieces[p.idx].r = m.r; game.pieces[p.idx].c = m.c; 
                let vWalls = game.getValidWalls(m.r, m.c); 
                
                vWalls.forEach(w => {
                    game.walls.set(`${w.r},${w.c}`, aiColor);
                    
                    let score = this.evaluateBoard(game, aiColor);
                    score += Math.random() * 0.01; 

                    if (score > bestScore) {
                        bestScore = score;
                        bestAction = { pIdx: p.idx, mr: m.r, mc: m.c, wr: w.r, wc: w.c };
                    }
                    game.walls.delete(`${w.r},${w.c}`);
                });
                game.pieces[p.idx].r = oldR; game.pieces[p.idx].c = oldC; 
            });
        });

        return bestAction;
    }
}