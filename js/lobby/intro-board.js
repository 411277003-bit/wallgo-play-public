// 背景棋盤動畫與開場動畫（棋子被牆困住 → 打破逃出）、跳過開場、動畫開關
// （大廳的 script 都是一般 <script>，共用全域變數；載入順序寫在 index.html）

/* ═════════ 背景：Wall Go 對局模擬（棋子移動 + 建牆） ═════════ */
const cv = document.getElementById('board'), ctx = cv.getContext('2d');
/* SQUASH=1：棋盤格不再壓扁，7×7 就是一個正方形。
   棋子頂面另外用 PIECE_SQUASH 保持橢圓，維持斜視的立體感。 */
const N = 7, SHEAR = 0, SQUASH = 1, PIECE_SQUASH = .58;
let REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches
           || localStorage.getItem('wallGoAnim') === 'off';

const C = {
  light:'#f7f1e3', line:'#a9c8dc', rim:'#b8553d', rimEdge:'#b8553d', edge:'#16253d',
  /* 四位玩家，每人兩子；牆的顏色＝棋子的顏色 */
  p:[{body:'#c4442d', top:'#d8583f', wall:'#c4442d', wallSide:'#9e3320'},
     {body:'#2c4a7c', top:'#3f66a3', wall:'#2c4a7c', wallSide:'#1d3355'},
     {body:'#e8b12e', top:'#f5c94f', wall:'#e8b12e', wallSide:'#bd8a16'},
     {body:'#4c8a45', top:'#5fa456', wall:'#4c8a45', wallSide:'#376630'}]
};

let W, H, S, OX, OY;

/* 版面有兩種：開場動畫置中，開場結束（登入卡出現）後棋盤讓到右半邊。
   layoutT 是兩者之間的插值，0=置中、1=靠右，在 draw() 裡緩動過去。
   視窗太窄時左右分欄擠不下，一律維持置中（與 CSS 的 900px 斷點一致）。 */
const LAYOUT_MIN_W = 900;
let layoutT = 0, layoutTarget = 0;

/* 靠右版面要與左側登入區塊等高，所以直接量它的實際高度。
   量一次快取起來，避免每幀 getBoundingClientRect 造成重排。 */
/* 大廳左右都有 UI：選單項目 hover 展開 322px、側欄卡片展開 338px。
   棋盤置中，所以每一側都要讓出「兩邊之中較寬的那塊」再加間隙。
   內距會隨斷點改變，因此量實際位置而不是寫死；量不到時用預設值。 */
const MENU_OPEN_W = 322, CARD_OPEN_W = 338, LOBBY_GAP = 40;
let lobbyReserve = 34 + CARD_OPEN_W + LOBBY_GAP;
function measureLobby(){
  const menu = document.querySelector('.menu'), side = document.querySelector('.side');
  if (!menu || !side) return;
  const m = menu.getBoundingClientRect(), r = side.getBoundingClientRect();
  if (!m.width || !r.width) return;                     /* 大廳還沒顯示 */
  lobbyReserve = Math.max(m.left + MENU_OPEN_W, innerWidth - r.right + CARD_OPEN_W) + LOBBY_GAP;
}
let inLobby = false;

let authBox = null;
function measureAuth(){
  const el = document.querySelector('.auth-inner');
  if(!el){ authBox = null; return; }
  const r = el.getBoundingClientRect();
  authBox = r.height > 120
    ? { h: r.height, w: r.width, left: r.left, right: r.right }
    : null;
}

function setLayout(t, instant){
  layoutTarget = t;
  if(t) measureAuth();
  /* 背景動畫關閉時沒有每幀的 draw() 來做緩動，必須當場定位並重畫一次，
     否則棋盤會停在載入時的置中位置，壓到登入卡或側欄 */
  if(instant || REDUCED){ layoutT = t; applyLayout(); }
  if(REDUCED) draw(0);
}

/* 棋盤含深藍外框是 N+0.7 格寬（drawBoard 從 -0.35 畫到 N+0.35），
   底下還有 shadowOffsetY 22 ＋ blur 50 的投影。尺寸要按這個總跨距算，
   否則外框會貼齊甚至超出視窗底部。 */
const FRAME_SPAN = N + 0.7;
/* 投影是固定像素（不隨 S 縮放），所以要直接從垂直預算裡扣掉，
   否則小螢幕上投影的邊緣會被視窗底部切掉。 */
const SHADOW_PAD = 60;

function applyLayout(){
  const t = W >= LAYOUT_MIN_W ? layoutT : 0;
  /* 上下各留一份 SHADOW_PAD，外框才能真正置中而不是被投影擠得偏上 */
  const availH = Math.max(H - SHADOW_PAD*2, 160);
  const sH = availH / FRAME_SPAN;
  /* 置中：整個視窗都可用；靠右：只剩右側約 55% 的寬度 */
  const s0 = inLobby
    ? Math.min(Math.max(W - lobbyReserve*2, 260)/FRAME_SPAN, sH)
    : Math.min(W/(FRAME_SPAN+0.6), sH);

  /* 靠右時與左側登入區塊對稱：外框高度與它相同，且棋盤右邊距 ==
     登入區塊左邊距，左右才會一樣寬；垂直一律取視窗正中，上下才會一樣高。 */
  let s1 = Math.min(W*0.55/(FRAME_SPAN+0.3), sH);
  let cx1 = W * 0.71;
  if(authBox){
    const margin = authBox.left;                       /* 目標邊距＝登入區塊的左邊距 */
    const room   = W - 2*margin - authBox.w - 40;      /* 扣掉登入區塊與 40px 間隙 */
    s1  = Math.min(s1, authBox.h/FRAME_SPAN, Math.max(room, 200)/FRAME_SPAN);
    cx1 = W - margin - FRAME_SPAN*s1/2;                /* 右緣落在 W - margin */
  }

  S  = Math.max(s0 + (s1-s0)*t, 40);
  OX = W*0.5 + (cx1 - W*0.5) * t;
  OY = H/2;

  /* 矮視窗上登入區塊可能偏離中心，夾住上下不讓外框與投影被切掉 */
  const half = FRAME_SPAN*S/2, lo = half + 8, hi = H - SHADOW_PAD - half;
  if(hi > lo) OY = Math.min(Math.max(OY, lo), hi);
}

function resize(){
  const dpr = Math.min(devicePixelRatio||1, 2);
  W = innerWidth; H = innerHeight;
  cv.width = W*dpr; cv.height = H*dpr;
  cv.style.width = W+'px'; cv.style.height = H+'px';
  ctx.setTransform(dpr,0,0,dpr,0,0);
  if(layoutTarget) measureAuth();
  if(inLobby) measureLobby();
  applyLayout();
}
addEventListener('resize', resize); resize();

const proj = (x,y,z=0)=>({
  X: OX + (x-N/2)*S + (y-N/2)*S*SHEAR,
  Y: OY + (y-N/2)*S*SQUASH - z
});

/* 狀態 */
let pieces=[], walls=new Map(), turn=0, moveCount=0;
const kH=(x,y)=>x+','+y+',H', kV=(x,y)=>x+','+y+',V';

function initBg(){
  pieces=[]; walls.clear(); turn=0; moveCount=0;
  breakers=[true,true,true,true]; lastBreak=-99;   /* 每種顏色一局只有一次破牆機會 */
  const spots=[[1,1],[5,5], [5,1],[1,5], [3,1],[3,5], [1,3],[5,3]];
  spots.forEach((s,i)=>pieces.push({p:Math.floor(i/2), x:s[0], y:s[1], dx:s[0], dy:s[1]}));
}
const occupied=(x,y)=>pieces.some(o=>o.x===x&&o.y===y);
function blocked(x,y,nx,ny){
  if(ny===y-1) return walls.has(kH(x,y));
  if(ny===y+1) return walls.has(kH(x,y+1));
  if(nx===x-1) return walls.has(kV(x,y));
  return walls.has(kV(x+1,y));
}
function reach(pc){
  const seen=new Map([[pc.x+','+pc.y,[]]]); let frontier=[[pc.x,pc.y,[]]];
  for(let step=0;step<2;step++){
    const next=[];
    for(const [x,y,path] of frontier){
      for(const [dx,dy] of [[0,-1],[0,1],[-1,0],[1,0]]){
        const nx=x+dx, ny=y+dy, k=nx+','+ny;
        if(nx<0||ny<0||nx>=N||ny>=N||seen.has(k)) continue;
        if(blocked(x,y,nx,ny)||occupied(nx,ny)) continue;
        const np=path.concat([[nx,ny]]); seen.set(k,np); next.push([nx,ny,np]);
      }
    }
    frontier=next;
  }
  seen.delete(pc.x+','+pc.y);
  return [...seen.values()];
}
function wallSpots(x,y){
  const o=[];
  if(y>0 && !walls.has(kH(x,y))) o.push(kH(x,y));
  if(y<N-1 && !walls.has(kH(x,y+1))) o.push(kH(x,y+1));
  if(x>0 && !walls.has(kV(x,y))) o.push(kV(x,y));
  if(x<N-1 && !walls.has(kV(x+1,y))) o.push(kV(x+1,y));
  return o;
}
const pick=a=>a[Math.floor(Math.random()*a.length)];

/* 回合流程 */
let phase='idle', t0=0, actor=null, path=[], from=null, newWall=null, fade=0;

/* ═ 破牆：碎片與衝擊波 ═ */
let shards=[], bursts=[], breakers=[true,true,true,true], lastBreak=-99;

/* ═ 開場動畫：棋子被四面牆困住 → 長出手臂打破 → 逃出 ═ */
let introHero=null, armAlpha=0, hammerAng=0, introSmashed=false, shake=0, cageKeys=[];
let impact=null, NOW=0, introStage=null;

/* 牆：footprint 半厚 WALL_T、浮起位移 WALL_D（單位：格）。
   關鍵在浮起是往「左上」的等量斜向位移，而不是只往上 —— 只往上的話
   位移量只加在 Y 軸，對橫牆是加在厚度、對直牆是加在長度，兩個方向
   永遠不可能一樣大。斜向位移同時加在 X 與 Y，兩者的視覺尺寸就都是
   (2*WALL_T + WALL_D) × (1 + WALL_D) 格，是同一個形狀轉 90 度。
   WALL_D 不宜過大，否則整排牆看起來會像斜的。 */
const WALL_T = 0.065, WALL_D = 0.07;
const WALL_VIS = 2*WALL_T + WALL_D;

const JOLT_ZERO = { z:0, ox:0, oy:0 };
/* 座標雜湊：同一格每幀都得到同一組亂數，物件才不會逐幀抖動 */
function hash01(n){ const v = Math.sin(n)*43758.5453; return v - Math.floor(v); }

/* 依據距離延遲的震波：越遠越晚跳、越遠幅度越小，並以阻尼彈跳收斂。
   除了往上彈，也沿著「震央 → 物件」的方向推開；每個物件再依座標雜湊
   取得固定但互不相同的偏轉角與強度，所以不會全部朝同一邊、跳同樣高。 */
function joltAt(x, y){
  if(!impact) return JOLT_ZERO;
  const dist = Math.hypot(x-impact.x, y-impact.y);
  const p = (NOW-impact.t)/1000 - dist*0.052;
  if(p<0 || p>1.15) return JOLT_ZERO;

  const h1 = hash01(x*12.9898 + y*78.233);    /* 決定跳多高 */
  const h2 = hash01(x*39.3468 + y*11.135);    /* 決定往哪偏 */

  const decay = Math.exp(-dist*0.20) * Math.exp(-p*3.4);
  const z = Math.abs(Math.sin(p*13)) * decay * S*1.25 * (0.65 + h1*0.85);

  const ang  = Math.atan2(y-impact.y, x-impact.x) + (h2-0.5)*1.9;   /* ±0.95 rad */
  const push = Math.sin(Math.min(p,1)*Math.PI) * decay * (0.26 + h1*0.30);
  return { z, ox: Math.cos(ang)*push, oy: Math.sin(ang)*push };
}
const REST_ANG=-0.35, RAISE_ANG=-2.45, SLAM_ANG=0.62;
const HAS_SESSION = !!localStorage.getItem('wallGoSession');

const INTRO_MOVES=3;                 /* 開場先正常走幾步再收網 */
function startIntro(now){
  pieces=[]; walls.clear(); shards=[]; bursts=[]; turn=0; moveCount=0;
  const cx=3, cy=3;
  pieces.push({p:0, x:cx, y:cy, dx:cx, dy:cy});
  introHero=pieces[0];
  /* 週邊零星的棋子與牆，開場那幾步由它們演出 */
  [[1,1,1],[5,1,1],[6,2,2],[1,6,3],[5,6,2],[6,6,0]].forEach(([x,y,p])=>pieces.push({p, x, y, dx:x, dy:y}));
  [[kH(1,1),1],[kV(6,2),2],[kH(1,6),3],[kV(2,1),1]].forEach(([k,p])=>walls.set(k,{p,t:0}));
  armAlpha=0; hammerAng=REST_ANG; introSmashed=false; shake=0;
  cageKeys=[]; introStage='play';
  phase='idle'; t0=now;
}

/* 三步過後，四面牆一道一道彈出來把主角關住 */
function buildCage(now){
  const cx=introHero.x, cy=introHero.y;
  cageKeys=[kH(cx,cy), kH(cx,cy+1), kV(cx,cy), kV(cx+1,cy)];
  cageKeys.forEach((k,i)=>{
    walls.set(k, {p:[1,2,3,1][i], t:now+i*90});
    setTimeout(()=>playSfx('wall'), i*90);   /* 一道一道彈出，聲音跟著錯開 */
  });
}

/* 圓角矩形（舊瀏覽器沒有 roundRect 時退回直角） */
function rrect(x,y,w,h,r){
  ctx.beginPath();
  if(ctx.roundRect) ctx.roundRect(x,y,w,h,r); else ctx.rect(x,y,w,h);
}

/* 手臂 + 槌子：以肩膀為支點旋轉，ang 為 0 時水平向右、負值往上舉 */
function drawHammer(pc, ang, alpha){
  if(alpha<=0.02) return;
  const c=proj(pc.dx+.5, pc.dy+.5), rx=S*.26, h=S*.40;
  const col=C.p[pc.p];
  const sx=c.X+rx*0.72, sy=c.Y-h*0.58;
  ctx.save(); ctx.globalAlpha=alpha;
  ctx.translate(sx,sy); ctx.rotate(ang); ctx.lineCap='round';

  /* 手臂 */
  const armLen=S*0.26;
  ctx.beginPath(); ctx.moveTo(0,0); ctx.lineTo(armLen,0);
  ctx.strokeStyle=C.edge; ctx.lineWidth=S*0.100; ctx.stroke();
  ctx.strokeStyle=col.body; ctx.lineWidth=S*0.058; ctx.stroke();
  /* 拳頭 */
  ctx.beginPath(); ctx.arc(armLen,0,S*0.072,0,7);
  ctx.fillStyle=col.top; ctx.fill();
  ctx.strokeStyle=C.edge; ctx.lineWidth=2.4; ctx.stroke();

  /* 槌柄 */
  ctx.translate(armLen,0);
  const hl=S*0.32, hw=S*0.052;
  ctx.beginPath(); ctx.moveTo(-S*0.03,0); ctx.lineTo(hl,0);
  ctx.strokeStyle=C.edge; ctx.lineWidth=hw+5; ctx.stroke();
  ctx.strokeStyle='#c98b45'; ctx.lineWidth=hw; ctx.stroke();
  /* 槌頭（與柄垂直的方塊） */
  const hd=S*0.15, hh=S*0.30;
  ctx.translate(hl,0);
  rrect(-hd/2,-hh/2,hd,hh,S*0.035);
  ctx.fillStyle='#586274'; ctx.fill();
  ctx.strokeStyle=C.edge; ctx.lineWidth=2.8; ctx.stroke();
  rrect(-hd/2,-hh/2,hd,hh*0.34,S*0.035);
  ctx.fillStyle='#6f7a8d'; ctx.fill();
  ctx.restore();
}
function smashWall(key, info, now){
  playSfx('break');
  const [xs,ys,d]=key.split(','); const x=+xs, y=+ys;
  const col=C.p[info.p];
  const cx = d==='H' ? x+0.5 : x;
  const cy = d==='H' ? y : y+0.5;
  bursts.push({x:cx, y:cy, t:now, col:'#ffffff', r0:0.10, r1:0.42, dur:240});
  bursts.push({x:cx, y:cy, t:now, col:col.wall,  r0:0.14, r1:0.78, dur:520});
  bursts.push({x:cx, y:cy, t:now, col:C.edge,    r0:0.12, r1:0.60, dur:400});
  for(let i=0;i<24;i++){
    const a=Math.random()*Math.PI*2, sp=0.010+Math.random()*0.026;
    shards.push({
      x: cx + (d==='H' ? (Math.random()-0.5)*0.9 : (Math.random()-0.5)*0.18),
      y: cy + (d==='H' ? (Math.random()-0.5)*0.18 : (Math.random()-0.5)*0.9),
      z: S*0.05 + Math.random()*S*0.24,
      vx: Math.cos(a)*sp, vy: Math.sin(a)*sp*0.55,
      vz: S*0.016 + Math.random()*S*0.038,
      rot: Math.random()*Math.PI, vr:(Math.random()-0.5)*0.35,
      w: S*(0.05+Math.random()*0.06), h: S*(0.035+Math.random()*0.05),
      col: Math.random()<0.55 ? col.wall : col.wallSide,
      life: 1
    });
  }
}
function stepShards(){
  for(const p of shards){
    p.x+=p.vx; p.y+=p.vy; p.z+=p.vz; p.vz-=S*0.0024; p.rot+=p.vr; p.life-=0.014;
    if(p.z<0){ p.z=0; p.vz*=-0.34; p.vx*=0.66; p.vy*=0.66; p.vr*=0.6; }
  }
  if(shards.length) shards=shards.filter(p=>p.life>0);
  if(bursts.length) bursts=bursts.filter(b=>performance.now()-b.t<b.dur);
}
function drawShards(now){
  for(const b of bursts){
    const age=Math.min((now-b.t)/b.dur,1);
    const c=proj(b.x,b.y,S*0.10), r=S*(b.r0+(b.r1-b.r0)*(1-Math.pow(1-age,2)));
    ctx.save(); ctx.globalAlpha=(1-age)*0.9;
    ctx.beginPath(); ctx.ellipse(c.X,c.Y,r,r*SQUASH,0,0,7);
    ctx.strokeStyle=b.col; ctx.lineWidth=Math.max(1,5*(1-age)); ctx.stroke();
    ctx.restore();
  }
  for(const p of shards){
    const c=proj(p.x,p.y,p.z);
    ctx.save(); ctx.translate(c.X,c.Y); ctx.rotate(p.rot);
    ctx.globalAlpha=Math.max(0,Math.min(1,p.life*1.5));
    ctx.fillStyle=p.col; ctx.fillRect(-p.w/2,-p.h/2,p.w,p.h);
    ctx.strokeStyle=C.edge; ctx.lineWidth=1.1; ctx.strokeRect(-p.w/2,-p.h/2,p.w,p.h);
    ctx.restore();
  }
  ctx.globalAlpha=1;
}
/* 選一顆自己的棋子開始移動 */
function startMove(now){
  const side=turn%4;
  let mine=pieces.filter(p=>p.p===side).filter(p=>reach(p).length);
  if(introStage==='play') mine=mine.filter(p=>p!==introHero);   /* 主角先別動 */
  if(!mine.length && introStage==='play'){ turn++; phase='idle'; t0=now; return; }
  if(!mine.length){ phase='reset'; t0=now; return; }
  actor=pick(mine); const paths=reach(actor);
  path=pick(paths); from={x:actor.x,y:actor.y};
  phase='move'; t0=now;
  playSfx('move');
}
function nextTurn(now){
  if(moveCount>=36){ phase='reset'; t0=now; return; }
  const side=turn%4;
  /* 破牆：每色一局限一次，且與上次破牆至少隔 4 步，不會連續發生。
     破牆只是回合中的一個動作，敲完由同一位玩家接著移動、建牆。 */
  if(!introStage && breakers[side] && walls.size>=4 && moveCount-lastBreak>=4){
    const owned=[...walls.entries()].filter(([k,v])=>v.p===side);
    if(owned.length && Math.random()<0.3){
      breakers[side]=false; lastBreak=moveCount;
      const [k,info]=pick(owned);
      walls.delete(k); smashWall(k, info, now);
      phase='break'; t0=now; return;
    }
  }
  startMove(now);
}
const easeIO=t=>t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2;
const easeBack=t=>1+2.2*Math.pow(t-1,3)+1.4*Math.pow(t-1,2);

function step(now){
  if(phase==='introGate') return;   /* 畫面凍在開場起始盤面，等使用者點擊 */
  const el=now-t0;
  stepShards();
  if(shake>0) shake=Math.max(0, shake-0.019);
  if(phase==='introTrap'){
    /* 掙扎：左右抖動 */
    introHero.dx = introHero.x + Math.sin(el/52)*0.05;
    if(el>620){ introHero.dx=introHero.x; phase='introRaise'; t0=now; }
  }
  else if(phase==='introRaise'){
    /* 把槌子高高舉起，身體微微後仰蓄力 */
    const k=Math.min(el/560,1), e=1-Math.pow(1-k,3);
    hammerAng = REST_ANG + (RAISE_ANG-REST_ANG)*e;
    armAlpha = Math.min(1, el/160);
    introHero.dx = introHero.x - 0.045*e;
    if(k===1){ phase='introHold'; t0=now; }
  }
  else if(phase==='introHold'){
    /* 舉在最高點停一拍，槌子微微顫抖 */
    hammerAng = RAISE_ANG + Math.sin(el/28)*0.035;
    if(el>200){ phase='introSlam'; t0=now; }
  }
  else if(phase==='introSlam'){
    /* 用力往下砸 */
    const k=Math.min(el/130,1), e=k*k;
    hammerAng = RAISE_ANG + (SLAM_ANG-RAISE_ANG)*e;
    introHero.dx = introHero.x - 0.045*(1-e);
    if(k===1 && !introSmashed){
      introSmashed=true;
      shake=1;                                        /* 整個畫面震動 */
      impact={x:introHero.x+0.5, y:introHero.y+0.5, t:now};   /* 震央 */
      /* 只敲碎槌子那一側（右邊）的那一道牆 */
      const wk=cageKeys[3], info=walls.get(wk);
      if(info){ walls.delete(wk); smashWall(wk, info, now); }
      if(typeof onIntroBreak==='function') onIntroBreak();
      showSkip(false);                 /* 牆一破、登入卡開始滑入，就沒有東西可跳過了 */
    }
    if(el>330){ phase='introFree'; t0=now; }
  }
  else if(phase==='introFree'){
    /* 收槌，從破口往右逃出去 */
    armAlpha = Math.max(0, 1-el/300);
    hammerAng = SLAM_ANG - 0.9*Math.min(1, el/300);
    const k=Math.min(el/700,1), e=easeIO(k);
    introHero.dx = introHero.x + e;
    if(k===1){
      /* 不重置棋盤，就從這個局面接著下 */
      introHero.x += 1; introHero.dx = introHero.x;
      introHero=null; armAlpha=0; introStage=null; phase='idle'; t0=now;
      showSkip(false);
    }
  }
  else if(phase==='break' && el>900){ startMove(now); }
  else if(phase==='idle' && el>(introStage==='play'?260:820)) nextTurn(now);
  else if(phase==='move'){
    const k=Math.min(el/(introStage==='play'?470:620),1), e=easeIO(k), seg=path.length, f=e*seg;
    const i=Math.min(Math.floor(f),seg-1), lf=f-i;
    const a=i===0?[from.x,from.y]:path[i-1], b=path[i];
    actor.dx=a[0]+(b[0]-a[0])*lf; actor.dy=a[1]+(b[1]-a[1])*lf;
    if(k===1){
      const end=path[seg-1]; actor.x=end[0]; actor.y=end[1]; actor.dx=end[0]; actor.dy=end[1];
      const sp=wallSpots(actor.x,actor.y);
      if(sp.length){ newWall=pick(sp); walls.set(newWall,{p:actor.p,t:now}); playSfx('wall'); }
      phase='wall'; t0=now;
    }
  }
  else if(phase==='wall' && el>(introStage==='play'?350:520)){
    turn++; moveCount++;
    if(introStage==='play' && moveCount>=INTRO_MOVES){
      introStage='cage'; buildCage(now); phase='introCage'; t0=now;
    } else { phase='idle'; t0=now; }
  }
  else if(phase==='introCage' && el>780){ introStage='act'; phase='introTrap'; t0=now; }
  else if(phase==='reset'){
    fade=Math.min(el/700,1);
    if(fade===1){ initBg(); shards=[]; bursts=[]; fade=0; phase='idle'; t0=now; }
  }
}

/* 繪圖 */
function poly(pts){ ctx.beginPath(); ctx.moveTo(pts[0].X,pts[0].Y);
  for(let i=1;i<pts.length;i++) ctx.lineTo(pts[i].X,pts[i].Y); ctx.closePath(); }

function drawBoard(){
  const c=[proj(0,0),proj(N,0),proj(N,N),proj(0,N)];
  ctx.save(); ctx.shadowColor='rgba(40,70,95,.35)'; ctx.shadowBlur=50; ctx.shadowOffsetY=22;
  poly([proj(-.35,-.35),proj(N+.35,-.35),proj(N+.35,N+.35),proj(-.35,N+.35)]);
  ctx.fillStyle=C.rim; ctx.fill(); ctx.restore();

  /* 米白方格紙：整片同色，格子靠細格線分出來 */
  poly(c); ctx.fillStyle=C.light; ctx.fill();
  ctx.beginPath();
  for(let i=1;i<N;i++){
    const a=proj(i,0), b=proj(i,N), d=proj(0,i), e=proj(N,i);
    ctx.moveTo(a.X,a.Y); ctx.lineTo(b.X,b.Y); ctx.moveTo(d.X,d.Y); ctx.lineTo(e.X,e.Y);
  }
  ctx.strokeStyle=C.line; ctx.lineWidth=1; ctx.stroke();
  poly(c); ctx.strokeStyle='rgba(90,40,28,.45)'; ctx.lineWidth=2; ctx.stroke();
}

/* 往左上浮起 d 格的立體板：先用暗面填滿 base→top 之間的側牆，
   再把亮色頂面畫上去，暗面自然留在右下兩側（光源在左上）。 */
function slab(bx0,by0,bx1,by1,d,side,top,lift=0){
  const b=[proj(bx0,by0,lift),proj(bx1,by0,lift),proj(bx1,by1,lift),proj(bx0,by1,lift)];
  const u=[proj(bx0-d,by0-d,lift),proj(bx1-d,by0-d,lift),proj(bx1-d,by1-d,lift),proj(bx0-d,by1-d,lift)];
  ctx.fillStyle=side;
  for(let i=0;i<4;i++){ poly([b[i],b[(i+1)%4],u[(i+1)%4],u[i]]); ctx.fill(); }
  poly(u); ctx.fillStyle=top; ctx.fill();
}

function drawWall(key, info, now){
  const [xs,ys,dir]=key.split(','); const x=+xs,y=+ys;
  const age=Math.min((now-info.t)/420,1);
  let g=(info.t?easeBack(age):1);            /* 浮起的進度，easeBack 會微微過衝 */
  if(phase==='reset') g*=1-fade;
  if(g<=0.02) return;

  const col=C.p[info.p], T=WALL_T, D=WALL_D, d=D*g;
  const j = dir==='H' ? joltAt(x+0.5,y) : joltAt(x,y+0.5);

  /* footprint 精確貼齊格線、長度就是整整一格，不做任何內縮 ——
     相鄰的牆底面才會首尾相接、頂面也同樣相接，中間不會空出洞。
     動畫過程中頂面由 base 往左上升起，看起來就是牆浮出棋盤。 */
  if(dir==='H'){
    slab(x+j.ox, y-T+j.oy, x+1+j.ox, y+T+j.oy, d, col.wallSide, col.wall, j.z);
  } else {
    slab(x-T+j.ox, y+j.oy, x+T+j.ox, y+1+j.oy, d, col.wallSide, col.wall, j.z);
  }
}

function drawPiece(pc){
  const rx=S*.26, ry=rx*PIECE_SQUASH, h=S*.40;
  /* 揮槌的人不該被自己那一下震飛，否則棋子會跟手上的槌子脫節 */
  const j = pc===introHero ? JOLT_ZERO : joltAt(pc.dx+.5, pc.dy+.5);
  const lift=j.z, gx=pc.dx+.5+j.ox, gy=pc.dy+.5+j.oy;
  const g=proj(gx,gy);                        /* 地面位置（影子） */
  const c=proj(gx,gy,lift);                   /* 被震起後的位置 */
  const col=C.p[pc.p];
  const k=1-Math.min(lift/(S*1.30),0.62);     /* 飛越高，影子越小越淡 */
  ctx.save(); ctx.globalAlpha=.22*k; ctx.fillStyle='#16253d';
  ctx.beginPath(); ctx.ellipse(g.X+S*.06,g.Y+S*.03,rx*1.12*k,ry*1.1*k,0,0,7); ctx.fill(); ctx.restore();
  /* 柱身（含描邊） */
  ctx.beginPath();
  ctx.moveTo(c.X-rx, c.Y-h); ctx.lineTo(c.X-rx, c.Y);
  ctx.ellipse(c.X, c.Y, rx, ry, 0, Math.PI, 0, true);
  ctx.lineTo(c.X+rx, c.Y-h); ctx.closePath();
  ctx.fillStyle=col.body; ctx.fill();
  ctx.strokeStyle=C.edge; ctx.lineWidth=2; ctx.stroke();
  /* 頂面 */
  ctx.beginPath(); ctx.ellipse(c.X,c.Y-h,rx,ry,0,0,7);
  ctx.fillStyle=col.top; ctx.fill(); ctx.strokeStyle=C.edge; ctx.lineWidth=2; ctx.stroke();
  ctx.beginPath(); ctx.ellipse(c.X,c.Y-h,rx*.45,ry*.45,0,0,7);
  ctx.strokeStyle='rgba(22,37,61,.35)'; ctx.lineWidth=1.4; ctx.stroke();
}

function draw(now){
  NOW=now;
  if(layoutT !== layoutTarget){
    layoutT += (layoutTarget - layoutT) * 0.075;
    if(Math.abs(layoutTarget - layoutT) < 0.0015) layoutT = layoutTarget;
    applyLayout();
  }
  ctx.clearRect(0,0,W,H);
  ctx.save();
  if(shake>0){                       /* 重擊的螢幕震動 + 推鏡 */
    const a=shake*shake*S*0.42, z=1+shake*shake*0.06;
    ctx.translate(W/2,H/2); ctx.scale(z,z); ctx.translate(-W/2,-H/2);
    ctx.translate((Math.random()-0.5)*a, (Math.random()-0.5)*a*0.72);
  }
  drawBoard();
  const items=[];
  walls.forEach((v,k)=>{ const [x,y,d]=k.split(','); items.push({d:+y+(d==='V'?1:0), fn:()=>drawWall(k,v,now)}); });
  pieces.forEach(p=>items.push({d:p.dy+.55, fn:()=>drawPiece(p)}));
  items.sort((a,b)=>a.d-b.d).forEach(i=>i.fn());
  if(introHero) drawHammer(introHero, hammerAng, armAlpha);
  if(shards.length||bursts.length) drawShards(now);
  ctx.restore();
}

function drawStatic(){
  initBg();
  for(let i=0;i<9;i++){ const p=pick(pieces); const s=wallSpots(p.x,p.y); if(s.length) walls.set(pick(s),{p:p.p,t:0}); }
  layoutT = layoutTarget; applyLayout();     /* 動畫中途關掉時，直接跳到目標版面 */
  draw(0);
}

let rafId=null;
function startLoop(){
  if(rafId!==null) return;
  (function loop(now){ step(now); draw(now); rafId=requestAnimationFrame(loop); })(performance.now());
}
function stopLoop(){ if(rafId!==null){ cancelAnimationFrame(rafId); rafId=null; } }

/* 開場動畫要有音效，就必須先有一次使用者互動 —— 這是瀏覽器的自動播放政策，
   繞不過去。所以先把開場的起始盤面擺好、停在那裡，等使用者點一下再開演；
   那一下同時解鎖音訊，敲擊聲才出得來。 */
function armIntroGate(){
  startIntro(performance.now());        /* 只擺盤，不推進 */
  phase='introGate';
  const hint=document.getElementById('intro-gate');
  if(hint) hint.classList.add('on');
  const go=()=>{
    if(phase!=='introGate') return;
    if(hint) hint.classList.remove('on');
    phase='idle'; t0=performance.now();
  };
  ['pointerdown','keydown'].forEach(ev=>
    addEventListener(ev, go, { once:true, passive:true }));
  showSkip(true);
}

/* ── 跳過開場 ── */
function showSkip(on){
  const b=document.getElementById('intro-skip');
  if(b) b.classList.toggle('on', on);
}
function skipIntro(){
  if(introStage===null) return;
  const gate=document.getElementById('intro-gate');
  if(gate) gate.classList.remove('on');
  /* 籠子還沒被打破就直接拆掉，主角才不會被永遠關在裡面 */
  if(!introSmashed) cageKeys.forEach(k=>walls.delete(k));
  if(introHero){ introHero.dx=introHero.x; introHero.dy=introHero.y; }
  introHero=null; armAlpha=0; introSmashed=true; shake=0; impact=null;
  introStage=null;
  /* 正在演開場專屬的段落就收掉；一般的移動／建牆讓它自然走完 */
  if(phase.startsWith('intro')){ phase='idle'; t0=performance.now(); }
  showSkip(false);
  /* 登入卡還沒出現：直接就定位，不跑滑入動畫 */
  const el=document.getElementById('auth-page');
  if(el.classList.contains('intro-wait')){
    el.classList.remove('intro-wait');
    setLayout(1, true);
  }
}
addEventListener('keydown', e=>{
  if(e.code==='Space' && introStage!==null && !introSmashed){ e.preventDefault(); skipIntro(); }
});

initBg();
if(REDUCED) drawStatic();
else { if(!HAS_SESSION) armIntroGate(); startLoop(); }
addEventListener('resize',()=>{ if(REDUCED) draw(0); });

function toggleAnim(){
  REDUCED = !REDUCED;
  localStorage.setItem('wallGoAnim', REDUCED ? 'off' : 'on');
  if(REDUCED){ stopLoop(); drawStatic(); toast('背景動畫已關閉'); }
  else { initBg(); startLoop(); toast('背景動畫已開啟'); }
  syncSettingsUI();
}
