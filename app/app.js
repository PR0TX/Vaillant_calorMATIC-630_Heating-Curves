/* calorMATIC 630 • Heating Curves Web
   Model: Tflow = clamp(Tmin, Troom + Hc(s)*(Troom - Tout), Tmax)
   Hc(s) is interpolated from anchors (estimated from the official Vaillant chart).
*/

// ---- Calibration anchors for Hc(s) ----
const ANCHORS = [
  [0.2, 0.40],  // ~28°C @ 0°C
  [0.4, 0.70],
  [0.6, 1.00],
  [0.8, 1.40],
  [1.0, 1.75],  // ~55°C @ 0°C
  [1.2, 1.90],
  [1.5, 2.00],  // ~60°C @ 0°C
  [2.0, 2.25],  // ~65°C @ 0°C
  [2.5, 2.50],
  [3.0, 2.75],
  [3.5, 3.40],
  [4.0, 4.133], // ~82°C @ +5°C reference
];

const SLOPE_MIN = 0.2, SLOPE_MAX = 4.0;
const XRANGE = { min: 20, max: -20 };    // Vaillant style: warm → cold to the right
const YRANGE = { min: 20, max: 90 };

// ---- DOM ----
const $ = sel => document.querySelector(sel);

const inputs = {
  room: $('#room'), roomNum: $('#roomNum'),
  tout: $('#tout'), toutNum: $('#toutNum'),
  slope: $('#slope'), slopeNum: $('#slopeNum'),
  tmin: $('#tmin'), tminNum: $('#tminNum'),
  tmax: $('#tmax'), tmaxNum: $('#tmaxNum'),
  showAll: $('#showAll'),
  showGrid: $('#showGrid'),
  showGuides: $('#showGuides'),
  savePng: $('#savePng'),
  reset: $('#reset'),
  share: $('#share'),
  resultPill: $('#resultPill'),
  metaText: $('#metaText'),
  canvas: $('#plot'),
};

const state = {
  room: 20.0,
  tout: 0.0,
  slope: 1.0,
  tmin: 25,
  tmax: 75,   // min allowed for Tmax is 40 (enforced by input attributes in HTML)
  showAll: true,
  showGrid: true,
  showGuides: true,
};

// ---- Helpers ----
function clamp(v, a, b){ return Math.max(a, Math.min(b, v)); }

function hcFromSlope(s){
  const sClamped = clamp(s, ANCHORS[0][0], ANCHORS[ANCHORS.length-1][0]);
  // linear interpolate between closest anchors
  for(let i=0;i<ANCHORS.length-1;i++){
    const [s0,h0] = ANCHORS[i];
    const [s1,h1] = ANCHORS[i+1];
    if(sClamped >= s0 && sClamped <= s1){
      const t = (sClamped - s0) / (s1 - s0);
      return h0 + t * (h1 - h0);
    }
  }
  // fallback (edge)
  return ANCHORS[ANCHORS.length-1][1];
}

function tflow(room, tout, slope, tmin, tmax){
  const hc = hcFromSlope(slope);
  const tf = room + hc * (room - tout);
  return clamp(tf, tmin, tmax);
}

function fmt(n, p=1){
  const s = (+n).toFixed(p);
  // trim trailing .0
  return s.replace(/\.0$/, '');
}

// ---- Canvas/Chart ----
const ctx = inputs.canvas.getContext('2d');

function resizeCanvas(){
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  const w = inputs.canvas.clientWidth;
  const h = inputs.canvas.clientHeight;
  inputs.canvas.width = Math.round(w * dpr);
  inputs.canvas.height = Math.round(h * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function mapX(x){
  // domain 20..-20 → pixel 0..W
  const { width } = inputs.canvas.getBoundingClientRect();
  const t = (x - XRANGE.min) / (XRANGE.max - XRANGE.min);
  return t * width;
}
function mapY(y){
  // domain 20..90 → pixel H..0 (inverted)
  const { height } = inputs.canvas.getBoundingClientRect();
  const t = (y - YRANGE.min) / (YRANGE.max - YRANGE.min);
  return height - t * height;
}

function drawGrid(){
  const { width, height } = inputs.canvas.getBoundingClientRect();
  ctx.strokeStyle = 'rgba(255,255,255,0.10)';
  ctx.lineWidth = 1;

  // Vertical lines every 5°C from +20 down to -20
  for(let x=20; x>=-20; x-=5){
    const px = mapX(x);
    ctx.beginPath();
    ctx.moveTo(px, 0);
    ctx.lineTo(px, height);
    ctx.stroke();

    ctx.fillStyle = 'rgba(255,255,255,0.65)';
    ctx.font = '12px system-ui, -apple-system, Segoe UI, Roboto';
    ctx.textAlign = 'center';
    ctx.fillText(fmt(x,0), px, height - 6);
  }

  // Horizontal lines every 10°C from 20..90
  for(let y=20; y<=90; y+=10){
    const py = mapY(y);
    ctx.beginPath();
    ctx.moveTo(0, py);
    ctx.lineTo(width, py);
    ctx.stroke();

    ctx.fillStyle = 'rgba(255,255,255,0.65)';
    ctx.font = '12px system-ui, -apple-system, Segoe UI, Roboto';
    ctx.textAlign = 'left';
    ctx.fillText(fmt(y,0), 6, py - 4);
  }
}

function plotCurve(room, tmin, tmax, slope, style){
  const { width, height } = inputs.canvas.getBoundingClientRect();
  const steps = 400;
  ctx.beginPath();
  for(let i=0;i<=steps;i++){
    const x = XRANGE.min + (i/steps) * (XRANGE.max - XRANGE.min);
    const y = tflow(room, x, slope, tmin, tmax);
    const px = mapX(x), py = mapY(y);
    if(i===0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  }
  ctx.strokeStyle = style.color;
  ctx.lineWidth = style.width || 1.2;
  ctx.globalAlpha = style.alpha ?? 1.0;
  ctx.stroke();
  ctx.globalAlpha = 1.0;

  // annotate a few labels
  if(style.label){
    const xi = -18;
    const yi = tflow(room, xi, slope, tmin, tmax);
    const px = mapX(xi), py = mapY(yi);
    ctx.fillStyle = 'rgba(255,255,255,0.8)';
    ctx.font = '11px system-ui, -apple-system, Segoe UI, Roboto';
    ctx.fillText(style.label, px + 6, py - 6);
  }
}

function drawGuides(tmin, tmax){
  // 18/20/22 °C guide families (using hc at slope 1.0 just як довідник)
  const guideRoom = [18, 20, 22];
  for(const rt of guideRoom){
    plotCurve(rt, tmin, tmax, 1.0, { color: 'rgba(255,255,255,0.35)', width: 1, alpha: .35 });
  }
}

function drawPoint(x, y){
  const px = mapX(x), py = mapY(y);
  ctx.fillStyle = '#22c55e';
  ctx.beginPath();
  ctx.arc(px, py, 5, 0, Math.PI*2);
  ctx.fill();
  ctx.strokeStyle = 'rgba(34,197,94,.35)';
  ctx.lineWidth = 10;
  ctx.beginPath(); ctx.arc(px, py, 10, 0, Math.PI*2); ctx.stroke();
}

function redraw(){
  resizeCanvas();
  ctx.clearRect(0,0,inputs.canvas.width,inputs.canvas.height);

  // background
  const { width, height } = inputs.canvas.getBoundingClientRect();
  const grad = ctx.createLinearGradient(0,0,0,height);
  grad.addColorStop(0, '#0b1224'); grad.addColorStop(1, '#0f172a');
  ctx.fillStyle = grad;
  ctx.fillRect(0,0,width,height);

  // current state
  const room  = state.room;
  const tout  = state.tout;
  const slope = state.slope;
  const tmin  = state.tmin;
  const tmax  = state.tmax;

  if(state.showGrid) drawGrid();
  if(state.showGuides) drawGuides(tmin, tmax);

  // all curves faint
  if(state.showAll){
    // залишаємо крок 0.2 тільки для «підписаних» орієнтирів; вибрана крива може бути будь-якою (із сотими)
    for(let s = SLOPE_MIN; s <= SLOPE_MAX + 1e-6; s += 0.2){
      const rounded = Math.round(s*10)/10;
      plotCurve(room, tmin, tmax, rounded, { color:'rgba(255,255,255,0.35)', alpha:0.35,
                                             width:1, label: [0.2,0.6,1.0,1.5,2.0,2.5,3.0,4.0].includes(+rounded) ? String(rounded) : null });
    }
  }

  // selected curve strong
  plotCurve(room, tmin, tmax, slope, { color:'#e5e7eb', width:2.4 });

  // current point
  const tf = tflow(room, tout, slope, tmin, tmax);
  drawPoint(tout, tf);

  // UI text (показуємо slope з точністю до сотих)
  inputs.resultPill.textContent = `Подача: ${fmt(tf,1)} °C`;
  inputs.metaText.textContent = `s=${fmt(slope,2)}, Tкімн=${fmt(room,1)} °C, Tзовн=${fmt(tout,0)} °C, Tmin=${fmt(tmin,0)} °C, Tmax=${fmt(tmax,0)} °C`;
}

// ---- Bindings ----
function couple(rangeEl, numEl, key, snap=val=>val){
  const sync = (from, to) => () => {
    let v = parseFloat(from.value);
    if(isNaN(v)) return;
    // enforce bounds
    const min = parseFloat(from.min), max = parseFloat(from.max);
    v = clamp(v, min, max);
    v = snap(v);
    from.value = v;
    to.value = v;
    state[key] = v;
    redraw();
    updateUrl();
  };
  rangeEl.addEventListener('input', sync(rangeEl, numEl));
  numEl.addEventListener('input', sync(numEl, rangeEl));
}

function updateUrl(){
  // encode current state as query for easy sharing
  const params = new URLSearchParams({
    r: state.room, o: state.tout, s: state.slope,
    n: state.tmin, x: state.tmax,
    a: state.showAll ? 1 : 0, g: state.showGrid ? 1 : 0, d: state.showGuides ? 1 : 0
  });
  history.replaceState(null, '', `?${params.toString()}`);
}

function readUrl(){
  const q = new URLSearchParams(location.search);
  const pick = (k, def)=> (q.has(k) ? parseFloat(q.get(k)) : def);
  const pickB = (k, def)=> (q.has(k) ? q.get(k) === '1' : def);
  state.room = pick('r', state.room);
  state.tout = pick('o', state.tout);
  state.slope = pick('s', state.slope);
  state.tmin = pick('n', state.tmin);
  state.tmax = pick('x', state.tmax);
  state.showAll = pickB('a', state.showAll);
  state.showGrid = pickB('g', state.showGrid);
  state.showGuides = pickB('d', state.showGuides);

  inputs.room.value = inputs.roomNum.value = state.room;
  inputs.tout.value = inputs.toutNum.value = state.tout;
  inputs.slope.value = inputs.slopeNum.value = state.slope;
  inputs.tmin.value = inputs.tminNum.value = state.tmin;
  inputs.tmax.value = inputs.tmaxNum.value = state.tmax;
  inputs.showAll.checked = state.showAll;
  inputs.showGrid.checked = state.showGrid;
  inputs.showGuides.checked = state.showGuides;
}

function init(){
  // ✅ робимо slope кроком 0.01 (і для повзунка, і для числового поля), не змінюючи HTML
  inputs.slope.step = "0.01";
  inputs.slopeNum.step = "0.01";

  // couple inputs
  couple(inputs.room,  inputs.roomNum,  'room',  v=>Math.round(v*10)/10);
  couple(inputs.tout,  inputs.toutNum,  'tout',  v=>Math.round(v));
  // ✅ slope тепер округляємо до СОТИХ:
  couple(inputs.slope, inputs.slopeNum, 'slope', v=>Math.round(v*100)/100);
  couple(inputs.tmin,  inputs.tminNum,  'tmin',  v=>Math.round(v));
  couple(inputs.tmax,  inputs.tmaxNum,  'tmax',  v=>Math.round(v));

  inputs.showAll.addEventListener('change', e=>{ state.showAll = e.target.checked; redraw(); updateUrl(); });
  inputs.showGrid.addEventListener('change', e=>{ state.showGrid = e.target.checked; redraw(); updateUrl(); });
  inputs.showGuides.addEventListener('change', e=>{ state.showGuides = e.target.checked; redraw(); updateUrl(); });

  inputs.reset.addEventListener('click', ()=>{
    inputs.room.value = inputs.roomNum.value = state.room = 20.0;
    inputs.tout.value = inputs.toutNum.value = state.tout = 0.0;
    inputs.slope.value = inputs.slopeNum.value = state.slope = 1.0;
    inputs.tmin.value = inputs.tminNum.value = state.tmin = 25;
    inputs.tmax.value = inputs.tmaxNum.value = state.tmax = 75;
    inputs.showAll.checked = state.showAll = true;
    inputs.showGrid.checked = state.showGrid = true;
    inputs.showGuides.checked = state.showGuides = true;
    redraw(); updateUrl();
  });

  inputs.savePng.addEventListener('click', ()=>{
    const link = document.createElement('a');
    const dt = new Date();
    const stamp = dt.toISOString().replace(/[:.]/g,'-');
    link.download = `heating-curves_${stamp}.png`;
    link.href = inputs.canvas.toDataURL('image/png');
    link.click();
  });

  inputs.share.addEventListener('click', async ()=>{
    const url = location.href;
    try{
      await navigator.clipboard.writeText(url);
      inputs.share.textContent = 'Скопійовано!';
      setTimeout(()=> inputs.share.textContent = 'Поділитися посиланням', 1200);
    }catch{
      alert(url);
    }
  });

  // responsive
  const ro = new ResizeObserver(()=> redraw());
  ro.observe(inputs.canvas);

  readUrl();
  redraw();
}

document.addEventListener('DOMContentLoaded', init);
