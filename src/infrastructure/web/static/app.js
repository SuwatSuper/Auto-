/* ════════════════════════════════════════════════════════════════
   THE KINGDOM PRIME — app.js
   AI-Powered Investment Ecosystem Dashboard
   Real-time WebSocket data · 20 Agent Emotions · Chart.js charts
   Vanilla ES2022 — no framework dependency
════════════════════════════════════════════════════════════════ */
'use strict';

/* ──────────────────────────────────────────────────────────────
   HELPERS
────────────────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);
const el = (tag, cls, txt) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt !== undefined) e.textContent = txt;
  return e;
};
const fmtNum = new Intl.NumberFormat('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtThb = n => '฿ ' + fmtNum.format(Number(n));
const clamp  = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

/* ──────────────────────────────────────────────────────────────
   20 EMOTIONS SYSTEM
   Each emotion has an id, label, emoji, and associated color
────────────────────────────────────────────────────────────── */
const EMOTIONS = [
  { id: 'ecstatic',    label: 'Ecstatic',    emoji: '🤩', color: '#00e676' },
  { id: 'happy',       label: 'Happy',       emoji: '😊', color: '#69f0ae' },
  { id: 'excited',     label: 'Excited',     emoji: '😄', color: '#ffd740' },
  { id: 'confident',   label: 'Confident',   emoji: '😎', color: '#40c4ff' },
  { id: 'focused',     label: 'Focused',     emoji: '🧐', color: '#2979ff' },
  { id: 'calm',        label: 'Calm',        emoji: '😌', color: '#80deea' },
  { id: 'curious',     label: 'Curious',     emoji: '🤔', color: '#ce93d8' },
  { id: 'determined',  label: 'Determined',  emoji: '😤', color: '#ffb74d' },
  { id: 'satisfied',   label: 'Satisfied',   emoji: '😏', color: '#a5d6a7' },
  { id: 'neutral',     label: 'Neutral',     emoji: '😐', color: '#90a4ae' },
  { id: 'cautious',    label: 'Cautious',    emoji: '🤨', color: '#fff176' },
  { id: 'anxious',     label: 'Anxious',     emoji: '😟', color: '#ffcc02' },
  { id: 'stressed',    label: 'Stressed',    emoji: '😰', color: '#ff9800' },
  { id: 'worried',     label: 'Worried',     emoji: '😧', color: '#ff7043' },
  { id: 'tired',       label: 'Tired',       emoji: '😴', color: '#b0bec5' },
  { id: 'overwhelmed', label: 'Overwhelmed', emoji: '😵', color: '#ef9a9a' },
  { id: 'frustrated',  label: 'Frustrated',  emoji: '😤', color: '#f44336' },
  { id: 'panicked',    label: 'Panicked',    emoji: '😱', color: '#e53935' },
  { id: 'angry',       label: 'Angry',       emoji: '😡', color: '#b71c1c' },
  { id: 'sleeping',    label: 'Sleeping',    emoji: '💤', color: '#78909c' },
];

// Build a fast lookup map: id → emotion object
const EMOTION_MAP = Object.fromEntries(EMOTIONS.map(e => [e.id, e]));

/**
 * Determine the current emotion id for an agent given its metrics.
 * Priority order: extreme states first, then positive states.
 * @param {{morale:number, stress:number, fatigue:number, confidence:number}} metrics
 * @returns {string} emotion id
 */
function getEmotion(metrics) {
  const { morale = 70, stress = 20, fatigue = 20, confidence = 70 } = metrics;
  if (fatigue > 85)                    return 'sleeping';
  if (stress > 85)                     return 'angry';
  if (stress > 80)                     return 'panicked';
  if (stress > 70 && fatigue > 60)     return 'overwhelmed';
  if (stress > 70)                     return 'frustrated';
  if (stress > 65)                     return 'worried';
  if (stress > 55)                     return 'stressed';
  if (fatigue > 70)                    return 'tired';
  if (stress > 45)                     return 'anxious';
  if (stress > 35)                     return 'cautious';
  if (morale > 90 && confidence > 90)  return 'ecstatic';
  if (morale > 80 && confidence > 75)  return 'happy';
  if (confidence > 80 && stress < 30)  return 'excited';
  if (confidence > 70 && morale > 65)  return 'confident';
  if (morale > 65 && stress < 40)      return 'satisfied';
  if (fatigue < 30 && stress < 30)     return 'calm';
  if (morale > 55)                     return 'determined';
  if (confidence > 55)                 return 'focused';
  if (morale > 45)                     return 'curious';
  return 'neutral';
}

/* ──────────────────────────────────────────────────────────────
   AGENT DEFINITIONS (7 agents matching image)
────────────────────────────────────────────────────────────── */
const AGENT_DEFS = [
  {
    id: 'market_analyst',
    label: 'Market Analyst',
    statusText: 'Analyzing…',
    hairColor: '#93c5fd', bodyColor: '#1d4ed8', skinColor: '#fde68a',
    accessory: 'chart',
    initialMetrics: { morale: 85, stress: 15, fatigue: 20, confidence: 88 },
  },
  {
    id: 'news_sentiment',
    label: 'News Intelligence',
    statusText: 'Monitoring…',
    hairColor: '#f9a8d4', bodyColor: '#be185d', skinColor: '#fecaca',
    accessory: 'antenna',
    initialMetrics: { morale: 80, stress: 22, fatigue: 25, confidence: 82 },
  },
  {
    id: 'risk',
    label: 'Risk Management',
    statusText: 'Protecting…',
    hairColor: '#86efac', bodyColor: '#15803d', skinColor: '#bbf7d0',
    accessory: 'shield',
    initialMetrics: { morale: 90, stress: 10, fatigue: 18, confidence: 92 },
  },
  {
    id: 'entry_exit',
    label: 'Execution Agent',
    statusText: 'Executing…',
    hairColor: '#fcd34d', bodyColor: '#b45309', skinColor: '#fde68a',
    accessory: 'sword',
    initialMetrics: { morale: 95, stress: 8, fatigue: 15, confidence: 96 },
  },
  {
    id: 'probability',
    label: 'Rebalancing',
    statusText: 'Optimizing…',
    hairColor: '#c4b5fd', bodyColor: '#7c3aed', skinColor: '#ede9fe',
    accessory: 'crystal',
    initialMetrics: { morale: 78, stress: 28, fatigue: 30, confidence: 80 },
  },
  {
    id: 'simulation',
    label: 'Compliance Agent',
    statusText: 'Verifying…',
    hairColor: '#94a3b8', bodyColor: '#334155', skinColor: '#f1f5f9',
    accessory: 'book',
    initialMetrics: { morale: 88, stress: 12, fatigue: 20, confidence: 90 },
  },
  {
    id: 'supreme',
    label: 'Capital Guardian',
    statusText: 'Preserving…',
    hairColor: '#fde047', bodyColor: '#a16207', skinColor: '#fef3c7',
    accessory: 'crown',
    initialMetrics: { morale: 97, stress: 5, fatigue: 10, confidence: 98 },
  },
];

/* ──────────────────────────────────────────────────────────────
   SVG CHIBI BUILDER
────────────────────────────────────────────────────────────── */
function buildEyesSVG(emoId) {
  switch (emoId) {
    case 'ecstatic': case 'happy': case 'excited':
      return `
        <path d="M11 14 Q14 17 17 14" stroke="#f97316" stroke-width="1.2" fill="none" stroke-linecap="round"/>
        <path d="M10 11 Q12 9 14 11" stroke="#fff" stroke-width="1.5" fill="none"/>
        <path d="M14 11 Q16 9 18 11" stroke="#fff" stroke-width="1.5" fill="none"/>`;
    case 'sleeping':
      return `
        <path d="M10 11 Q12 11 14 11" stroke="#94a3b8" stroke-width="1.5" fill="none"/>
        <path d="M14 11 Q16 11 18 11" stroke="#94a3b8" stroke-width="1.5" fill="none"/>
        <path d="M12 14 Q14 15 16 14" stroke="#94a3b8" stroke-width="1" fill="none"/>
        <text x="17" y="9" font-size="5" fill="#93c5fd">z</text><text x="19" y="7" font-size="4" fill="#93c5fd">z</text>`;
    case 'worried': case 'anxious': case 'panicked':
      return `
        <line x1="10" y1="10" x2="14" y2="12" stroke="#fff" stroke-width="1.5"/>
        <line x1="14" y1="10" x2="10" y2="12" stroke="#fff" stroke-width="1.5"/>
        <line x1="14" y1="10" x2="18" y2="12" stroke="#fff" stroke-width="1.5"/>
        <line x1="18" y1="10" x2="14" y2="12" stroke="#fff" stroke-width="1.5"/>
        <path d="M11 15 Q14 13 17 15" stroke="#f97316" stroke-width="1.2" fill="none"/>`;
    case 'angry': case 'frustrated':
      return `
        <line x1="10" y1="9" x2="14" y2="11" stroke="#fff" stroke-width="1.5"/>
        <circle cx="12" cy="11.5" r="2" fill="#fff"/><circle cx="12.5" cy="11.5" r="1" fill="#1e293b"/>
        <line x1="14" y1="9" x2="18" y2="11" stroke="#fff" stroke-width="1.5"/>
        <circle cx="16" cy="11.5" r="2" fill="#fff"/><circle cx="16.5" cy="11.5" r="1" fill="#1e293b"/>
        <path d="M11 15 Q14 13 17 15" stroke="#f97316" stroke-width="1.2" fill="none"/>`;
    case 'tired': case 'overwhelmed':
      return `
        <line x1="10" y1="11" x2="14" y2="11" stroke="#94a3b8" stroke-width="1.5"/>
        <line x1="14" y1="11" x2="18" y2="11" stroke="#94a3b8" stroke-width="1.5"/>
        <path d="M12 14 Q14 15 16 14" stroke="#94a3b8" stroke-width="1" fill="none"/>`;
    case 'confident': case 'satisfied': case 'determined':
      return `
        <circle cx="12" cy="11" r="2.5" fill="#fff"/><circle cx="12.5" cy="11" r="1.2" fill="#1e293b"/>
        <circle cx="16" cy="11" r="2.5" fill="#fff"/><circle cx="16.5" cy="11" r="1.2" fill="#1e293b"/>
        <path d="M11 14 Q14 16 17 14" stroke="#f97316" stroke-width="1.2" fill="none" stroke-linecap="round"/>`;
    case 'curious':
      return `
        <circle cx="12" cy="11" r="2.5" fill="#fff"/><circle cx="13" cy="10.5" r="1.2" fill="#1e293b"/>
        <circle cx="16" cy="11" r="2.5" fill="#fff"/><circle cx="17" cy="10.5" r="1.2" fill="#1e293b"/>
        <path d="M12 14.5 Q14 16 16 14.5" stroke="#f97316" stroke-width="1" fill="none"/>`;
    default: // neutral, cautious, stressed, focused, calm
      return `
        <circle cx="12" cy="11" r="2.5" fill="#fff"/><circle cx="12.5" cy="11" r="1.2" fill="#1e293b"/>
        <circle cx="16" cy="11" r="2.5" fill="#fff"/><circle cx="16.5" cy="11" r="1.2" fill="#1e293b"/>
        <path d="M12 15 Q14 16 16 15" stroke="#f97316" stroke-width="1" fill="none"/>`;
  }
}

function buildAccessorySVG(type, bodyColor, accentColor) {
  switch (type) {
    case 'chart':
      return `<rect x="17" y="27" width="11" height="8" rx="1" fill="#0a1525" stroke="${accentColor}" stroke-width="0.6"/>
              <line x1="19" y1="32" x2="19" y2="34" stroke="${accentColor}" stroke-width="1.2"/>
              <line x1="21" y1="30" x2="21" y2="34" stroke="${accentColor}" stroke-width="1.2"/>
              <line x1="23" y1="31" x2="23" y2="34" stroke="${accentColor}" stroke-width="1.2"/>
              <line x1="25" y1="29" x2="25" y2="34" stroke="${accentColor}" stroke-width="1.2"/>`;
    case 'antenna':
      return `<line x1="24" y1="2" x2="24" y2="8" stroke="${accentColor}" stroke-width="1.2"/>
              <circle cx="24" cy="2" r="1.5" fill="${accentColor}" opacity="0.9"/>
              <circle cx="24" cy="2" r="3" fill="${accentColor}" opacity="0.3"/>`;
    case 'shield':
      return `<path d="M16 27 L16 34 Q16 37 20 39 Q24 37 24 34 L24 27 Z" fill="${bodyColor}" stroke="${accentColor}" stroke-width="1"/>
              <line x1="20" y1="29" x2="20" y2="36" stroke="${accentColor}" stroke-width="0.8"/>
              <line x1="17" y1="32" x2="23" y2="32" stroke="${accentColor}" stroke-width="0.8"/>`;
    case 'sword':
      return `<line x1="26" y1="20" x2="18" y2="40" stroke="#e2e8f0" stroke-width="2" stroke-linecap="round"/>
              <line x1="21" y1="32" x2="25" y2="30" stroke="#94a3b8" stroke-width="1.5"/>
              <circle cx="26" cy="20" r="2" fill="${accentColor}"/>`;
    case 'crystal':
      return `<polygon points="20,22 17,30 23,30" fill="${accentColor}" opacity="0.8"/>
              <polygon points="20,22 23,30 27,26" fill="${bodyColor}" opacity="0.7"/>
              <circle cx="20" cy="22" r="2.5" fill="#fff" opacity="0.5"/>`;
    case 'book':
      return `<rect x="17" y="27" width="10" height="12" rx="1" fill="#1e3a5f" stroke="${accentColor}" stroke-width="0.7"/>
              <line x1="22" y1="27" x2="22" y2="39" stroke="${accentColor}" stroke-width="0.7"/>
              <line x1="18" y1="30" x2="21" y2="30" stroke="${accentColor}" stroke-width="0.5"/>
              <line x1="18" y1="32" x2="21" y2="32" stroke="${accentColor}" stroke-width="0.5"/>`;
    case 'crown':
      return `<polygon points="13,8 16,2 20,8 24,2 27,8 27,13 13,13" fill="${accentColor}" stroke="#b45309" stroke-width="0.7"/>
              <circle cx="16" cy="5" r="1.5" fill="#f87171"/>
              <circle cx="20" cy="3" r="2" fill="#60a5fa"/>
              <circle cx="24" cy="5" r="1.5" fill="#34d399"/>`;
    default:
      return '';
  }
}

function buildChibiSVG(def, emoId) {
  const { hairColor, bodyColor, skinColor, accessory } = def;
  const emo = EMOTIONS[emoId] || EMOTIONS.neutral;
  const accentColor = emo.color;
  const eyes = buildEyesSVG(emoId);
  const acc  = buildAccessorySVG(accessory, bodyColor, accentColor);
  const blushOpacity = ['happy','ecstatic','excited','confident'].includes(emoId) ? '0.5' : '0.1';

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 50" width="44" height="55">
  <!-- Shadow -->
  <ellipse cx="20" cy="47" rx="10" ry="3" fill="#000" opacity="0.3"/>
  <!-- Legs -->
  <rect x="13" y="34" width="5" height="9" rx="2.5" fill="${bodyColor}"/>
  <rect x="22" y="34" width="5" height="9" rx="2.5" fill="${bodyColor}"/>
  <!-- Feet -->
  <ellipse cx="15.5" cy="43" rx="4" ry="2.5" fill="#1e293b"/>
  <ellipse cx="24.5" cy="43" rx="4" ry="2.5" fill="#1e293b"/>
  <!-- Torso -->
  <rect x="11" y="22" width="18" height="15" rx="4" fill="${bodyColor}"/>
  <!-- Arms -->
  <rect x="5"  y="24" width="7"  height="7" rx="3.5" fill="${bodyColor}"/>
  <rect x="28" y="24" width="7"  height="7" rx="3.5" fill="${bodyColor}"/>
  <!-- Neck -->
  <rect x="17" y="19" width="6" height="5" rx="2.5" fill="${skinColor}"/>
  <!-- Head -->
  <ellipse cx="20" cy="12" rx="11" ry="12" fill="${skinColor}"/>
  <!-- Hair back -->
  <ellipse cx="20" cy="6" rx="11" ry="7" fill="${hairColor}"/>
  <!-- Blush -->
  <circle cx="11" cy="14" r="3" fill="#f9a8d4" opacity="${blushOpacity}"/>
  <circle cx="29" cy="14" r="3" fill="#f9a8d4" opacity="${blushOpacity}"/>
  <!-- Eyes & mouth -->
  ${eyes}
  <!-- Accessory -->
  ${acc}
  <!-- Aura glow at feet -->
  <ellipse cx="20" cy="44" rx="9" ry="2.5" fill="${accentColor}" opacity="0.2"/>
</svg>`;
}

/* ──────────────────────────────────────────────────────────────
   APP STATE
────────────────────────────────────────────────────────────── */
const State = {
  prices: [],
  latestPrice: null,
  prevPrice: null,
  equity: null,
  pnlToday: null,
  positions: 0,
  winRate: null,
  dailyLossPct: 0,
  drawdownPct: 0,
  killSwitch: false,
  uptimeSeconds: 0,
  mode: 'simulator',
  wsRetryDelay: 1500,
  wsRetryTimer: null,
  lang: 'en',
  agents: {},
  agentMetrics: {},
  notifCount: 3,
  charts: { perf: null, donut: null },
};

// Seed agent metrics
AGENT_DEFS.forEach(d => {
  State.agentMetrics[d.id] = { ...d.initialMetrics };
});

/* ──────────────────────────────────────────────────────────────
   PORTFOLIO ALLOCATION DATA
────────────────────────────────────────────────────────────── */
const ALLOC_DATA = [
  { label: 'Bitcoin',  pct: 45.2, color: '#f97316' },
  { label: 'Ethereum', pct: 20.1, color: '#8b5cf6' },
  { label: 'USDT',     pct: 15.3, color: '#22d3ee' },
  { label: 'Solana',   pct: 7.8,  color: '#84cc16' },
  { label: 'Others',   pct: 11.6, color: '#6366f1' },
];

/* ──────────────────────────────────────────────────────────────
   CLOCK
────────────────────────────────────────────────────────────── */
function updateClock() {
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  $('clock-time').textContent =
    `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  const days = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  $('clock-date').textContent =
    `${days[now.getDay()]}, ${months[now.getMonth()]} ${now.getDate()}, ${now.getFullYear()}`;
}
setInterval(updateClock, 1000);
updateClock();

/* ──────────────────────────────────────────────────────────────
   WEBSOCKET
────────────────────────────────────────────────────────────── */
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onopen = () => {
    setConnState(true);
    State.wsRetryDelay = 1500;
  };

  ws.onclose = ws.onerror = () => {
    setConnState(false);
    scheduleReconnect();
  };

  ws.onmessage = ({ data }) => {
    try {
      const msg = JSON.parse(data);
      if (msg.type === 'price')  handlePrice(msg.data);
      if (msg.type === 'status') handleStatus(msg.data);
    } catch (_) {}
  };
}

function setConnState(connected) {
  const led  = $('conn-led');
  const txt  = $('conn-text');
  if (connected) {
    led.classList.add('connected');
    txt.textContent = 'Connected';
  } else {
    led.classList.remove('connected');
    txt.textContent = 'Reconnecting…';
  }
}

function scheduleReconnect() {
  clearTimeout(State.wsRetryTimer);
  State.wsRetryTimer = setTimeout(() => {
    State.wsRetryDelay = Math.min(State.wsRetryDelay * 2, 30000);
    connectWS();
  }, State.wsRetryDelay);
}

/* ──────────────────────────────────────────────────────────────
   DATA HANDLERS
────────────────────────────────────────────────────────────── */
function handlePrice(data) {
  const price = Number(data.price ?? data.close ?? data.value ?? 0);
  if (!price) return;
  State.prevPrice    = State.latestPrice;
  State.latestPrice  = price;
  State.prices.push({ t: Date.now(), v: price });
  if (State.prices.length > 200) State.prices.shift();
  renderPrice();
  updatePerfChart();
}

function handleStatus(data) {
  State.equity         = data.equity ?? State.equity;
  State.pnlToday       = data.pnl_today ?? State.pnlToday;
  State.positions      = data.positions ?? data.open_positions ?? 0;
  State.winRate        = data.win_rate ?? State.winRate;
  State.dailyLossPct   = data.daily_loss_pct ?? 0;
  State.drawdownPct    = data.drawdown_pct ?? 0;
  State.killSwitch     = data.kill_switch ?? false;
  State.uptimeSeconds  = data.uptime_seconds ?? 0;
  State.mode           = data.mode ?? 'simulator';
  State.agents         = data.agents ?? {};

  renderPortfolio();
  renderRisk();
  renderUptime();
  renderModeBtn();
  updateAgentCards();
  simulateAgentMetrics();
}

/* ──────────────────────────────────────────────────────────────
   RENDER FUNCTIONS
────────────────────────────────────────────────────────────── */
function renderPrice() {
  const p = State.latestPrice;
  if (!p) return;
  const prev = State.prevPrice || p;
  const arrow = p >= prev ? '▲' : '▼';
  const cls   = p >= prev ? 'positive' : 'negative';
  const diff  = ((p - prev) / prev * 100).toFixed(4);

  $('stat-btc-price').textContent = fmtThb(p);
  const chg = $('stat-btc-change');
  chg.textContent = `${arrow} ${Math.abs(diff)}%  Live`;
  chg.className = 'stat-change ' + cls;
  $('price-arrow').textContent = arrow;
}

function renderPortfolio() {
  const eq = State.equity;
  if (eq !== null) {
    $('stat-equity').textContent = fmtThb(eq);
    $('city-equity').textContent = fmtThb(eq);
    // Cash reserve = 12.45% of equity
    const cash = eq * 0.1245;
    $('cash-amount').textContent = fmtThb(cash);
  }
  const pnl = State.pnlToday;
  if (pnl !== null) {
    const pnlEl = $('stat-pnl');
    if (pnlEl) pnlEl.textContent = (pnl >= 0 ? '+' : '') + fmtThb(pnl);
    const chgEl = $('stat-pnl-change');
    if (chgEl) {
      chgEl.textContent = pnl >= 0 ? '▲ Profit today' : '▼ Loss today';
      chgEl.className = 'stat-change ' + (pnl >= 0 ? 'positive' : 'negative');
    }
    $('city-pnl').textContent = (pnl >= 0 ? '+' : '') + fmtThb(pnl);
    $('city-pnl').className = 'city-metric-val ' + (pnl >= 0 ? 'green' : '');
  }
  if (State.winRate !== null) {
    const wr = (State.winRate * 100).toFixed(1);
    $('city-wr').textContent = wr + '%';
    $('city-winrate').textContent = wr + '% WIN';
  }
  $('city-positions').textContent = `${State.positions} POSITIONS`;
  $('stat-equity-change').textContent = '24H Portfolio Overview';
  $('stat-equity-change').className = 'stat-change positive';
  // Monthly return: estimate from pnl
  if (State.pnlToday !== null && State.equity) {
    const monthlyEst = ((State.pnlToday * 22) / State.equity * 100).toFixed(2);
    $('stat-monthly').textContent = monthlyEst + ' %';
  }
}

function renderRisk() {
  const dl  = (State.dailyLossPct * 100).toFixed(1);
  const dd  = (State.drawdownPct  * 100).toFixed(1);
  $('risk-daily').textContent = dl + '%';
  $('risk-dd').textContent    = dd + '%';

  const kill = $('kill-badge');
  if (State.killSwitch) {
    kill.textContent = 'ALERT';
    kill.className   = 'kill-badge alert';
  } else {
    kill.textContent = 'SAFE';
    kill.className   = 'kill-badge safe';
  }

  // Needle: max exposure is daily_loss + drawdown, range 0-100%
  const totalRisk = clamp((State.dailyLossPct + State.drawdownPct) * 50, 0, 100);
  const angle = -90 + (totalRisk / 100) * 180;
  const needle = $('risk-needle');
  if (needle) needle.style.transform = `rotate(${angle}deg)`;
}

function renderUptime() {
  const s  = Math.floor(State.uptimeSeconds);
  const h  = Math.floor(s / 3600);
  const m  = Math.floor((s % 3600) / 60);
  const sc = s % 60;
  const pad = n => String(n).padStart(2, '0');
  $('stat-uptime-val').textContent = `${pad(h)}:${pad(m)}:${pad(sc)}`;
}

function renderModeBtn() {
  const btnSim  = $('btn-sim');
  const btnLive = $('btn-live');
  if (State.mode === 'live') {
    btnSim.classList.remove('active');
    btnLive.classList.add('active');
    $('stat-mode-badge').textContent = 'LIVE MODE';
    $('stat-mode-badge').className   = 'stat-change positive';
  } else {
    btnLive.classList.remove('active');
    btnSim.classList.add('active');
    $('stat-mode-badge').textContent = 'SIMULATOR MODE';
    $('stat-mode-badge').className   = 'stat-change';
  }
}

/* ──────────────────────────────────────────────────────────────
   SIMULATE AGENT METRICS (gradual drift based on market)
────────────────────────────────────────────────────────────── */
function simulateAgentMetrics() {
  AGENT_DEFS.forEach(def => {
    const m = State.agentMetrics[def.id];
    if (!m) return;
    // Drift morale toward 80, stress toward 20, fatigue toward 25
    const drift = (target, cur, speed) => cur + (target - cur) * speed + (Math.random() - 0.5) * 4;
    m.morale     = clamp(drift(80, m.morale,     0.05), 0, 100);
    m.stress     = clamp(drift(20, m.stress,     0.05), 0, 100);
    m.fatigue    = clamp(drift(25, m.fatigue,    0.03), 0, 100);
    m.confidence = clamp(drift(82, m.confidence, 0.05), 0, 100);

    // If kill switch active, stress agents
    if (State.killSwitch) {
      m.stress  = clamp(m.stress  + 15, 0, 100);
      m.fatigue = clamp(m.fatigue + 8,  0, 100);
      m.morale  = clamp(m.morale  - 10, 0, 100);
    }
  });
}

/* ──────────────────────────────────────────────────────────────
   AGENT CARDS
────────────────────────────────────────────────────────────── */
function buildAgentCard(def) {
  const metrics = State.agentMetrics[def.id] || def.initialMetrics;
  const emoId   = getEmotion(metrics);
  const emo     = EMOTIONS[emoId];
  const runtime = State.agents[def.id] || {};
  const running = runtime.running !== false;
  const perf    = clamp(metrics.confidence, 50, 100);

  const card = el('div', `agent-card ${running ? 'running' : 'stopped'}`);
  card.id = `agent-card-${def.id}`;
  card.style.animationDelay = `${AGENT_DEFS.indexOf(def) * 0.06}s`;

  // Chibi avatar
  const avatarDiv = el('div', 'agent-chibi');
  avatarDiv.innerHTML = buildChibiSVG(def, emoId);
  const glow = el('div', 'agent-glow');
  glow.style.background = `${emo.color}50`;
  avatarDiv.appendChild(glow);
  card.appendChild(avatarDiv);

  // Name
  card.appendChild(el('div', 'agent-name', def.label));

  // Status row
  const statusRow = el('div', 'agent-status-row');
  const dot = el('span', `agent-dot ${running ? 'running' : ''}`);
  statusRow.appendChild(dot);
  statusRow.appendChild(el('span', 'agent-status-txt', running ? def.statusText : 'Idle'));
  card.appendChild(statusRow);

  // Emotion badge
  const badge = el('div', 'emotion-badge');
  badge.style.color = emo.color;
  badge.style.borderColor = emo.color + '60';
  badge.style.background  = emo.color + '18';
  badge.innerHTML = `${emo.emoji} ${emo.label}`;
  card.appendChild(badge);

  // Progress bar
  const barWrap = el('div', 'agent-bar-wrap');
  const barBg   = el('div', 'agent-bar-bg');
  const barFill = el('div', 'agent-bar-fill');
  barFill.style.width = perf.toFixed(1) + '%';
  barFill.style.background = `linear-gradient(90deg, ${emo.color}, #00e5ff)`;
  barBg.appendChild(barFill);
  barWrap.appendChild(barBg);
  const pctTxt = el('div', 'agent-bar-pct', perf.toFixed(0) + '%');
  barWrap.appendChild(pctTxt);
  card.appendChild(barWrap);

  // Buttons
  const btnRow = el('div', 'agent-btn-row');
  const btnStart = el('button', 'agent-btn start', '▶');
  const btnStop  = el('button', 'agent-btn stop',  '■');
  btnStart.onclick = () => apiPost(`/api/agents/${def.id}/start`);
  btnStop.onclick  = () => apiPost(`/api/agents/${def.id}/stop`);
  btnRow.appendChild(btnStart);
  btnRow.appendChild(btnStop);
  card.appendChild(btnRow);

  return card;
}

function renderAgentGrid() {
  const grid = $('agent-grid');
  grid.innerHTML = '';
  AGENT_DEFS.forEach(def => grid.appendChild(buildAgentCard(def)));
}

function updateAgentCards() {
  AGENT_DEFS.forEach(def => {
    const existing = $(`agent-card-${def.id}`);
    if (!existing) return;
    const metrics = State.agentMetrics[def.id] || def.initialMetrics;
    const emoId   = getEmotion(metrics);
    const emo     = EMOTIONS[emoId];
    const runtime = State.agents[def.id] || {};
    const running = runtime.running !== false;
    const perf    = clamp(metrics.confidence, 50, 100);

    // Update emotion badge
    const badge = existing.querySelector('.emotion-badge');
    if (badge) {
      badge.style.color = emo.color;
      badge.style.borderColor = emo.color + '60';
      badge.style.background  = emo.color + '18';
      badge.innerHTML = `${emo.emoji} ${emo.label}`;
    }
    // Update chibi avatar (face expression)
    const chibi = existing.querySelector('.agent-chibi');
    if (chibi) {
      chibi.innerHTML = buildChibiSVG(def, emoId);
      const glow = el('div', 'agent-glow');
      glow.style.background = `${emo.color}50`;
      chibi.appendChild(glow);
    }
    // Update status
    const dot = existing.querySelector('.agent-dot');
    const txt = existing.querySelector('.agent-status-txt');
    if (dot) { dot.className = `agent-dot ${running ? 'running' : ''}`; }
    if (txt) txt.textContent = running ? def.statusText : 'Idle';
    // Update bar
    const fill = existing.querySelector('.agent-bar-fill');
    const pct  = existing.querySelector('.agent-bar-pct');
    if (fill) {
      fill.style.width      = perf.toFixed(1) + '%';
      fill.style.background = `linear-gradient(90deg, ${emo.color}, #00e5ff)`;
    }
    if (pct) pct.textContent = perf.toFixed(0) + '%';
    // Card class
    existing.className = `agent-card ${running ? 'running' : 'stopped'}`;
  });
}

/* ──────────────────────────────────────────────────────────────
   CHARTS
────────────────────────────────────────────────────────────── */
function initDonutChart() {
  const ctx = document.getElementById('chart-donut');
  if (!ctx) return;
  State.charts.donut = new Chart(ctx.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: ALLOC_DATA.map(d => d.label),
      datasets: [{
        data: ALLOC_DATA.map(d => d.pct),
        backgroundColor: ALLOC_DATA.map(d => d.color + 'cc'),
        borderColor: ALLOC_DATA.map(d => d.color),
        borderWidth: 1.5,
        hoverOffset: 4,
      }],
    },
    options: {
      responsive: true,
      cutout: '70%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed.toFixed(1)}%` },
        },
      },
      animation: { duration: 600 },
    },
  });

  // Legend
  const legend = $('donut-legend');
  legend.innerHTML = '';
  ALLOC_DATA.forEach(d => {
    const row = el('div', 'donut-legend-item');
    const lbl = el('div', 'donut-legend-label');
    const dot = el('span', 'donut-legend-dot');
    dot.style.background = d.color;
    lbl.appendChild(dot);
    lbl.appendChild(document.createTextNode(d.label));
    row.appendChild(lbl);
    row.appendChild(el('span', 'donut-legend-pct', d.pct.toFixed(1) + '%'));
    legend.appendChild(row);
  });
}

function initPerfChart() {
  const ctx = document.getElementById('chart-perf');
  if (!ctx) return;
  const labels = Array.from({ length: 30 }, (_, i) => `${i + 1}`);
  const dummyData = labels.map((_, i) => 100 + Math.sin(i * 0.4) * 5 + i * 0.62);
  State.charts.perf = new Chart(ctx.getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Performance',
        data: dummyData,
        borderColor: '#00e676',
        backgroundColor: 'rgba(0,230,118,0.08)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.4,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { mode: 'index' } },
      scales: {
        x: { display: false },
        y: {
          display: true,
          ticks: { color: '#4a6080', font: { size: 9 }, maxTicksLimit: 4 },
          grid: { color: '#1a2740' },
          border: { display: false },
        },
      },
      animation: { duration: 300 },
    },
  });
}

function updatePerfChart() {
  const chart = State.charts.perf;
  if (!chart || State.prices.length < 2) return;
  const last30 = State.prices.slice(-30);
  const base   = last30[0].v;
  chart.data.labels = last30.map((_, i) => String(i + 1));
  chart.data.datasets[0].data = last30.map(p => ((p.v / base) * 100).toFixed(2));
  chart.update('none');
}

/* ──────────────────────────────────────────────────────────────
   API HELPERS
────────────────────────────────────────────────────────────── */
async function apiPost(url) {
  try {
    const r = await fetch(url, { method: 'POST' });
    return await r.json();
  } catch (_) { return null; }
}

async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    handleStatus(d);
  } catch (_) {}
}

/* ──────────────────────────────────────────────────────────────
   EVENT LISTENERS
────────────────────────────────────────────────────────────── */
function bindEvents() {
  // Mode buttons
  $('btn-sim').addEventListener('click', () => apiPost('/api/mode/simulator'));
  $('btn-live').addEventListener('click', () => apiPost('/api/mode/live'));

  // Emergency
  $('emergency-stop').addEventListener('click', async () => {
    await apiPost('/api/emergency_stop');
    $('emergency-stop').classList.add('hidden');
    $('emergency-reset').classList.remove('hidden');
  });
  $('emergency-reset').addEventListener('click', async () => {
    await apiPost('/api/emergency_reset');
    $('emergency-reset').classList.add('hidden');
    $('emergency-stop').classList.remove('hidden');
  });

  // Start/stop all
  $('start-all').addEventListener('click', () => apiPost('/api/agents/start_all'));
  $('stop-all').addEventListener('click',  () => apiPost('/api/agents/stop_all'));

  // Nav items
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', e => {
      e.preventDefault();
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      item.classList.add('active');
    });
  });

  // Language toggle
  $('lang-toggle').addEventListener('click', () => {
    State.lang = State.lang === 'en' ? 'th' : 'en';
    $('lang-toggle').textContent = State.lang === 'en' ? 'TH' : 'EN';
  });
}

/* ──────────────────────────────────────────────────────────────
   PERIODIC UPDATES
────────────────────────────────────────────────────────────── */
function startPeriodicUpdates() {
  // Refresh status every 2s
  setInterval(fetchStatus, 2000);
  // Simulate metrics drift every 3s
  setInterval(() => {
    simulateAgentMetrics();
    updateAgentCards();
  }, 3000);
  // Jitter notifications
  setInterval(() => {
    const delta = Math.random() < 0.3 ? 1 : 0;
    State.notifCount = Math.max(0, State.notifCount + delta);
    const badge = $('notif-badge');
    if (badge) badge.textContent = String(State.notifCount);
  }, 8000);
}

/* ──────────────────────────────────────────────────────────────
   INIT
────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  renderAgentGrid();
  initDonutChart();
  initPerfChart();
  bindEvents();
  connectWS();
  fetchStatus();
  startPeriodicUpdates();
  // Initial mock equity so dashboard doesn't appear empty
  handleStatus({
    equity: 1284567.89,
    pnl_today: 24567.89,
    positions: 3,
    win_rate: 0.724,
    daily_loss_pct: 0.012,
    drawdown_pct: 0.045,
    kill_switch: false,
    uptime_seconds: 0,
    mode: 'simulator',
    agents: Object.fromEntries(AGENT_DEFS.map(d => [d.id, { running: true }])),
  });
});
