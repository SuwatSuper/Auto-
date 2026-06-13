/* ═══════════════════════════════════════════════════════════════════
   Anime Bitcoin Operations Center — app.js
   Vanilla ES2022, no framework. Sections mirror spec 5.1–5.10.
═══════════════════════════════════════════════════════════════════ */
'use strict';

// ── Helpers ──────────────────────────────────────────────────────
const $  = (id) => document.getElementById(id);
const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt !== undefined) e.textContent = txt; return e; };
const fmt     = new Intl.NumberFormat('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtThb  = (n) => '฿ ' + fmt.format(Number(n));
const clamp   = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const pct     = (v, max) => clamp(Math.round((v / max) * 100), 0, 100);

// ═══════════════════════════════════════════════════════════════════
// 5.0  AppState  — single source of truth
// ═══════════════════════════════════════════════════════════════════
const AppState = {
  // prices
  prices: [],          // [{t, v}]
  latestPrice: null,
  prevPrice: null,

  // websocket
  wsRetryDelay: 1000,
  wsRetryTimer: null,

  // market mode
  marketMode: 'UNKNOWN',

  // gamification
  level: 1,
  xp: 0,
  xpPerLevel: 100,
  winStreak: 0,
  tradeCount: 0,
  achievements: [],

  // agent emotions (keyed by agent id)
  emotions: {},

  // portfolio
  equity: null,
  pnlToday: null,
  openPositions: 0,
  winRate: null,

  // risk
  dailyLossPct: 0,
  drawdownPct: 0,
  killSwitch: false,

  // agents runtime
  agents: {},    // { id: { running, msg_count } }

  // i18n
  lang: 'en',
  strings: { en: {}, th: {} },
};

// ═══════════════════════════════════════════════════════════════════
// 5.1  LAYOUT helpers
// ═══════════════════════════════════════════════════════════════════

// Default emotion values per agent
const AGENT_DEFS = [
  { id: 'news_sentiment',      label: 'News Analyst',  emoji: '📰', hairColor: '#4488ff', bodyColor: '#2255bb', accessory: 'book'   },
  { id: 'historical_research', label: 'Historian',     emoji: '📊', hairColor: '#88aacc', bodyColor: '#335577', accessory: 'scroll'  },
  { id: 'entry_exit',          label: 'Tactician',     emoji: '⚔️', hairColor: '#ff4444', bodyColor: '#882222', accessory: 'sword'   },
  { id: 'probability',         label: 'Oracle',        emoji: '🎲', hairColor: '#cc44ff', bodyColor: '#661199', accessory: 'crystal' },
  { id: 'risk',                label: 'Guardian',      emoji: '🛡️', hairColor: '#44ff88', bodyColor: '#226644', accessory: 'shield'  },
  { id: 'simulation',          label: 'Simulator',     emoji: '🔮', hairColor: '#cccccc', bodyColor: '#445566', accessory: 'laptop'  },
  { id: 'supreme',             label: 'Supreme Cmdr',  emoji: '👑', hairColor: '#ffd740', bodyColor: '#aa8800', accessory: 'crown'   },
];

// seed default emotions
AGENT_DEFS.forEach(a => {
  AppState.emotions[a.id] = { fatigue: 20, stress: 15, morale: 75, confidence: 70 };
});

// ═══════════════════════════════════════════════════════════════════
// 5.2  CHIBI SVG BUILDER
// ═══════════════════════════════════════════════════════════════════

function getExpression(emo) {
  if (emo.morale > 70 && emo.confidence > 70) return 'happy';
  if (emo.stress > 70)  return 'worried';
  if (emo.fatigue > 80) return 'tired';
  return 'neutral';
}

function buildEyesSVG(expr) {
  // returns SVG group string for eyes/mouth
  switch (expr) {
    case 'happy':
      // ^^ eyes, small smile
      return `
        <path d="M22 38 Q25 35 28 38" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round"/>
        <path d="M34 38 Q37 35 40 38" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round"/>
        <path d="M27 46 Q31 50 36 46" stroke="#ffaaaa" stroke-width="1.5" fill="none" stroke-linecap="round"/>
      `;
    case 'worried':
      // >< eyes, frown
      return `
        <line x1="22" y1="36" x2="28" y2="40" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
        <line x1="28" y1="36" x2="22" y2="40" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
        <line x1="34" y1="36" x2="40" y2="40" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
        <line x1="40" y1="36" x2="34" y2="40" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
        <path d="M27 48 Q31 44 36 48" stroke="#ffaaaa" stroke-width="1.5" fill="none" stroke-linecap="round"/>
      `;
    case 'tired':
      // -_- closed eyes, flat mouth
      return `
        <line x1="21" y1="38" x2="29" y2="38" stroke="#aaa" stroke-width="2" stroke-linecap="round"/>
        <line x1="33" y1="38" x2="41" y2="38" stroke="#aaa" stroke-width="2" stroke-linecap="round"/>
        <line x1="28" y1="47" x2="35" y2="47" stroke="#ffaaaa" stroke-width="1.5" stroke-linecap="round"/>
      `;
    default:
      // oo neutral
      return `
        <circle cx="25" cy="38" r="3.5" fill="#fff"/>
        <circle cx="37" cy="38" r="3.5" fill="#fff"/>
        <circle cx="26" cy="38" r="1.5" fill="#222"/>
        <circle cx="38" cy="38" r="1.5" fill="#222"/>
        <path d="M27 47 Q31 50 35 47" stroke="#ffaaaa" stroke-width="1.5" fill="none" stroke-linecap="round"/>
      `;
  }
}

function buildAccessorySVG(type, bodyColor) {
  switch (type) {
    case 'book':
      return `<rect x="46" y="54" width="14" height="11" rx="1" fill="#4488ff" stroke="#88bbff" stroke-width="0.5"/>
              <line x1="53" y1="54" x2="53" y2="65" stroke="#88bbff" stroke-width="1"/>`;
    case 'scroll':
      return `<rect x="43" y="55" width="16" height="10" rx="2" fill="#ccaa66" stroke="#ffdd88" stroke-width="0.5"/>
              <line x1="46" y1="58" x2="56" y2="58" stroke="#886633" stroke-width="1"/>
              <line x1="46" y1="61" x2="56" y2="61" stroke="#886633" stroke-width="1"/>`;
    case 'sword':
      return `<line x1="58" y1="44" x2="44" y2="72" stroke="#cccccc" stroke-width="2.5" stroke-linecap="round"/>
              <line x1="52" y1="56" x2="60" y2="56" stroke="#888" stroke-width="2" stroke-linecap="round"/>
              <circle cx="58.5" cy="44.5" r="2.5" fill="#ffdd55"/>`;
    case 'crystal':
      return `<polygon points="50,50 46,60 54,60" fill="#cc88ff" opacity="0.8"/>
              <polygon points="50,50 54,60 58,55" fill="#aa44ff" opacity="0.7"/>
              <circle cx="50" cy="50" r="3" fill="#ffffff" opacity="0.6"/>`;
    case 'shield':
      return `<path d="M47 54 L47 65 Q47 70 52 72 Q57 70 57 65 L57 54 Z" fill="${bodyColor}" stroke="#44ff88" stroke-width="1.5"/>
              <line x1="52" y1="56" x2="52" y2="68" stroke="#44ff88" stroke-width="1"/>
              <line x1="48" y1="62" x2="56" y2="62" stroke="#44ff88" stroke-width="1"/>`;
    case 'laptop':
      return `<rect x="42" y="60" width="18" height="11" rx="1" fill="#223344" stroke="#44aaff" stroke-width="0.8"/>
              <rect x="43" y="61" width="16" height="8" rx="0.5" fill="#112233"/>
              <line x1="45" y1="63" x2="55" y2="63" stroke="#44aaff" stroke-width="0.8"/>
              <line x1="45" y1="65" x2="52" y2="65" stroke="#44aaff" stroke-width="0.8"/>`;
    case 'crown':
      return `<polygon points="31,18 35,10 39,18 43,10 47,18 47,24 31,24" fill="#ffd740" stroke="#ffaa00" stroke-width="1"/>
              <circle cx="35" cy="13" r="2" fill="#ff4444"/>
              <circle cx="39" cy="10" r="2.5" fill="#44aaff"/>
              <circle cx="43" cy="13" r="2" fill="#44ff88"/>`;
    default: return '';
  }
}

function buildChibiSVG(def, expr) {
  const { hairColor, bodyColor, accessory } = def;
  const eyes = buildEyesSVG(expr);
  const acc  = buildAccessorySVG(accessory, bodyColor);
  // cheek blush color
  const blush = (expr === 'happy') ? 'opacity="0.6"' : 'opacity="0.2"';
  // For supreme, add throne behind
  const throne = (def.id === 'supreme') ? `
    <rect x="12" y="64" width="38" height="6" rx="2" fill="#886600" stroke="#ffd740" stroke-width="1"/>
    <rect x="10" y="58" width="7" height="14" rx="2" fill="#886600" stroke="#ffd740" stroke-width="1"/>
    <rect x="45" y="58" width="7" height="14" rx="2" fill="#886600" stroke="#ffd740" stroke-width="1"/>
    <rect x="22" y="55" width="18" height="12" rx="2" fill="#aa8800" stroke="#ffd740" stroke-width="1"/>
  ` : '';

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 62 78" width="62" height="78">
  <!-- body shadow -->
  <ellipse cx="31" cy="74" rx="16" ry="4" fill="#00000040"/>
  ${throne}
  <!-- legs -->
  <rect x="21" y="63" width="8" height="12" rx="3" fill="${bodyColor}"/>
  <rect x="33" y="63" width="8" height="12" rx="3" fill="${bodyColor}"/>
  <!-- feet -->
  <ellipse cx="25" cy="75" rx="5" ry="3" fill="#222"/>
  <ellipse cx="37" cy="75" rx="5" ry="3" fill="#222"/>
  <!-- torso -->
  <rect x="17" y="47" width="28" height="22" rx="6" fill="${bodyColor}"/>
  <!-- arms -->
  <rect x="7"  y="49" width="12" height="8" rx="4" fill="${bodyColor}"/>
  <rect x="43" y="49" width="12" height="8" rx="4" fill="${bodyColor}"/>
  <!-- neck -->
  <rect x="26" y="44" width="10" height="6" rx="3" fill="#ffccaa"/>
  <!-- head -->
  <ellipse cx="31" cy="33" rx="16" ry="17" fill="#ffccaa"/>
  <!-- hair back -->
  <ellipse cx="31" cy="20" rx="16" ry="9" fill="${hairColor}"/>
  <!-- hair front -->
  <path d="M15 28 Q14 15 22 12 Q31 8 40 12 Q48 15 47 28" fill="${hairColor}"/>
  <!-- hair bangs -->
  <path d="M16 26 Q18 18 22 20 Q20 26 22 30" fill="${hairColor}"/>
  <path d="M46 26 Q44 18 40 20 Q42 26 40 30" fill="${hairColor}"/>
  <!-- ears -->
  <ellipse cx="15" cy="34" rx="3.5" ry="4" fill="#ffccaa"/>
  <ellipse cx="47" cy="34" rx="3.5" ry="4" fill="#ffccaa"/>
  <!-- face -->
  ${eyes}
  <!-- nose -->
  <circle cx="31" cy="43" r="1.2" fill="#ffaaaa"/>
  <!-- cheeks -->
  <ellipse cx="21" cy="42" rx="4" ry="2.5" fill="#ff8888" ${blush}/>
  <ellipse cx="41" cy="42" rx="4" ry="2.5" fill="#ff8888" ${blush}/>
  <!-- accessory -->
  ${acc}
</svg>`;
}

// ═══════════════════════════════════════════════════════════════════
// 5.2 + 5.3  Build Chibi Zone DOM
// ═══════════════════════════════════════════════════════════════════

function buildAgentZone(def) {
  const zone = el('div', 'chibi-zone stopped');
  zone.id = `zone-${def.id}`;

  // SVG wrap — use innerHTML ONLY for static SVG (not user data)
  const svgWrap = el('div', 'chibi-svg-wrap');
  svgWrap.id = `svg-wrap-${def.id}`;
  const emo = AppState.emotions[def.id];
  svgWrap.innerHTML = buildChibiSVG(def, getExpression(emo)); // SVG is static, not user data

  // Name
  const name = el('div', 'chibi-name', `${def.emoji} ${def.label}`);

  // Status badge
  const status = el('div', 'chibi-status stopped');
  status.id = `status-${def.id}`;
  status.textContent = 'STOPPED';

  // Msg count
  const msgs = el('div', 'chibi-msgs', 'msgs: 0');
  msgs.id = `msgs-${def.id}`;

  // Emotion bars
  const bars = el('div', 'emotion-bars');
  ['fatigue','stress','morale','confidence'].forEach(key => {
    const row  = el('div', `emo-row emo-${key}`);
    const lbl  = el('span', 'emo-label', key[0].toUpperCase());
    const trk  = el('div', 'emo-track');
    const fill = el('div', 'emo-fill');
    fill.id    = `emo-${def.id}-${key}`;
    fill.style.width = emo[key] + '%';
    trk.appendChild(fill);
    row.appendChild(lbl);
    row.appendChild(trk);
    bars.appendChild(row);
  });

  zone.appendChild(svgWrap);
  zone.appendChild(name);
  zone.appendChild(status);
  zone.appendChild(msgs);
  zone.appendChild(bars);
  return zone;
}

function initAgentGrid() {
  const grid = $('agent-grid');
  AGENT_DEFS.forEach(def => {
    grid.appendChild(buildAgentZone(def));
  });
}

// ═══════════════════════════════════════════════════════════════════
// 5.3  Update agent emotions & expression
// ═══════════════════════════════════════════════════════════════════

function updateAgentEmotion(id, deltaEmo) {
  const emo = AppState.emotions[id];
  if (!emo) return;
  Object.assign(emo, deltaEmo);
  // clamp
  for (const k of ['fatigue','stress','morale','confidence']) emo[k] = clamp(emo[k], 0, 100);

  // update bars
  ['fatigue','stress','morale','confidence'].forEach(k => {
    const fill = $(`emo-${id}-${k}`);
    if (fill) fill.style.width = emo[k] + '%';
  });

  // update chibi expression
  const def = AGENT_DEFS.find(d => d.id === id);
  if (!def) return;
  const wrap = $(`svg-wrap-${id}`);
  if (wrap) wrap.innerHTML = buildChibiSVG(def, getExpression(emo));
}

// Gentle emotion drift driven by running state (no randomness)
function tickEmotions() {
  AGENT_DEFS.forEach(def => {
    const agent = AppState.agents[def.id];
    const running = agent?.running ?? false;
    const emo = AppState.emotions[def.id];
    if (running) {
      updateAgentEmotion(def.id, {
        fatigue:    Math.min(emo.fatigue    + 0.3, 100),
        stress:     Math.min(emo.stress     + 0.2, 100),
        morale:     Math.min(emo.morale     + 0.15, 100),
        confidence: Math.min(emo.confidence + 0.1, 100),
      });
    } else {
      // recovery when stopped
      updateAgentEmotion(def.id, {
        fatigue:    Math.max(emo.fatigue    - 0.4, 0),
        stress:     Math.max(emo.stress     - 0.4, 0),
        morale:     Math.max(emo.morale     - 0.2, 30),
        confidence: Math.max(emo.confidence - 0.1, 20),
      });
    }
  });
}
setInterval(tickEmotions, 3000);

// ═══════════════════════════════════════════════════════════════════
// 5.4  Market Mode Effects
// ═══════════════════════════════════════════════════════════════════

const MODE_CLASS = {
  TRENDING_UP:   'market-trending-up',
  TRENDING_DOWN: 'market-trending-down',
  RANGING:       'market-ranging',
  BREAKOUT:      'market-breakout',
  UNKNOWN:       'market-unknown',
};
const ALL_MODE_CLASSES = Object.values(MODE_CLASS);

function setMarketMode(mode) {
  if (AppState.marketMode === mode) return;
  AppState.marketMode = mode;
  // update body class
  document.body.classList.remove(...ALL_MODE_CLASSES);
  document.body.classList.add(MODE_CLASS[mode] ?? 'market-unknown');
  // update badge
  const badge = $('market-mode-badge');
  if (badge) {
    badge.textContent = mode;
    badge.className = 'market-mode-badge ' + (MODE_CLASS[mode] ? `mode-${MODE_CLASS[mode].replace('market-','')}` : '');
  }
}

// ═══════════════════════════════════════════════════════════════════
// 5.5  Gamification
// ═══════════════════════════════════════════════════════════════════

const ACHIEVEMENT_DEFS = [
  { id: 'first_trade',    label: '🎯 First Trade',    condition: (s) => s.tradeCount >= 1 },
  { id: 'streak_3',       label: '🔥 Hot Streak x3',  condition: (s) => s.winStreak >= 3 },
  { id: 'level_5',        label: '⭐ Level 5',         condition: (s) => s.level >= 5 },
  { id: 'hundred_trades', label: '💯 100 Trades',      condition: (s) => s.tradeCount >= 100 },
  { id: 'streak_10',      label: '🚀 Streak x10',      condition: (s) => s.winStreak >= 10 },
];

function addXP(amount) {
  AppState.xp += amount;
  const xpForNext = AppState.level * AppState.xpPerLevel;
  if (AppState.xp >= xpForNext) {
    AppState.xp -= xpForNext;
    AppState.level++;
    logEvent(`Level up! Now LVL ${AppState.level}`, 'trade');
  }
  renderGamification();
}

function recordTrade(isWin) {
  AppState.tradeCount++;
  if (isWin) {
    AppState.winStreak++;
    addXP(50);
  } else {
    AppState.winStreak = 0;
    addXP(10);
  }
  checkAchievements();
  renderGamification();
}

function checkAchievements() {
  ACHIEVEMENT_DEFS.forEach(def => {
    if (!AppState.achievements.includes(def.id) && def.condition(AppState)) {
      AppState.achievements.push(def.id);
      logEvent(`Achievement unlocked: ${def.label}`, 'trade');
    }
  });
}

function renderGamification() {
  const xpForNext = AppState.level * AppState.xpPerLevel;
  const xpPct     = pct(AppState.xp, xpForNext);

  const lvlEl = $('game-level');
  const xpEl  = $('game-xp');
  const xpMax = $('game-xp-max');
  const xpBar = $('xp-fill');
  const stk   = $('game-streak');
  const fire  = $('streak-fire');
  const trds  = $('game-trades');

  if (lvlEl) lvlEl.textContent = AppState.level;
  if (xpEl)  xpEl.textContent  = AppState.xp;
  if (xpMax) xpMax.textContent  = xpForNext;
  if (xpBar) xpBar.style.width  = xpPct + '%';
  if (stk)   stk.textContent    = AppState.winStreak;
  if (fire)  fire.textContent   = AppState.winStreak > 3 ? ' 🔥' : '';
  if (trds)  trds.textContent   = AppState.tradeCount;

  // render badges
  const row = $('achievements-row');
  if (!row) return;
  while (row.firstChild) row.removeChild(row.firstChild);
  // show last 3 earned, then next upcoming unearned
  const earned = ACHIEVEMENT_DEFS.filter(d => AppState.achievements.includes(d.id)).slice(-3);
  const upcoming = ACHIEVEMENT_DEFS.filter(d => !AppState.achievements.includes(d.id)).slice(0, Math.max(0, 3 - earned.length));
  [...earned, ...upcoming].forEach(def => {
    const badge = el('div', 'achievement-badge ' + (AppState.achievements.includes(def.id) ? 'earned' : ''));
    badge.textContent = def.label;
    row.appendChild(badge);
  });
}

// ═══════════════════════════════════════════════════════════════════
// 5.6  Price Chart (Chart.js)
// ═══════════════════════════════════════════════════════════════════

let priceChart = null;
let latestPricePt = null;
let lastChartTick  = 0;

function initChart() {
  const canvas = $('price-chart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  // gradient fill
  const gradient = ctx.createLinearGradient(0, 0, 0, 110);
  gradient.addColorStop(0, 'rgba(0,229,255,0.25)');
  gradient.addColorStop(1, 'rgba(0,229,255,0.00)');

  priceChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'BTC/THB',
        data: [],
        borderColor: '#00e5ff',
        backgroundColor: gradient,
        borderWidth: 1.5,
        tension: 0.3,
        pointRadius: 0,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      animation: false,
      maintainAspectRatio: false,
      scales: {
        x: {
          ticks: { color: '#3d5080', maxTicksLimit: 5, font: { size: 9 } },
          grid:  { color: '#1e2d5060' },
        },
        y: {
          ticks: {
            color: '#3d5080',
            font: { size: 9 },
            callback: (v) => fmt.format(v),
          },
          grid: { color: '#1e2d5060' },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0e1224',
          borderColor: '#1e2d50',
          borderWidth: 1,
          titleColor: '#8ca0cc',
          bodyColor: '#e8eeff',
          callbacks: { label: (ctx) => '฿ ' + fmt.format(ctx.parsed.y) },
        },
      },
    },
  });
}

function pushPricePoint(price, tsMs) {
  const ts = new Date(tsMs).toLocaleTimeString('th-TH', { hour12: false });
  latestPricePt = { t: ts, v: Number(price) };

  // update header display immediately
  const prev = AppState.prevPrice;
  const cur  = Number(price);
  AppState.prevPrice = AppState.latestPrice;
  AppState.latestPrice = cur;

  const display = $('price-display');
  const arrow   = $('price-arrow');
  const meta    = $('price-meta');

  if (display) display.textContent = fmt.format(cur);
  if (arrow) {
    if (prev === null || cur === prev) {
      arrow.textContent = '—';
      arrow.className   = 'price-arrow';
    } else if (cur > prev) {
      arrow.textContent = '↑';
      arrow.className   = 'price-arrow up';
    } else {
      arrow.textContent = '↓';
      arrow.className   = 'price-arrow down';
    }
  }
  if (meta) meta.textContent = `${ts}  ·  BTC/THB`;
}

// Chart samples at 1-second intervals
setInterval(() => {
  if (!latestPricePt || !priceChart) return;
  const now = Date.now();
  if (now - lastChartTick < 1000) return;
  lastChartTick = now;

  AppState.prices.push(latestPricePt);
  if (AppState.prices.length > 100) AppState.prices.shift();

  priceChart.data.labels                 = AppState.prices.map(p => p.t);
  priceChart.data.datasets[0].data       = AppState.prices.map(p => p.v);
  priceChart.update('none');
}, 250);

// ═══════════════════════════════════════════════════════════════════
// 5.7  Portfolio Panel
// ═══════════════════════════════════════════════════════════════════

function renderPortfolio({ equity, pnlToday, openPositions, winRate } = {}) {
  if (equity       != null) AppState.equity       = equity;
  if (pnlToday     != null) AppState.pnlToday     = pnlToday;
  if (openPositions!= null) AppState.openPositions = openPositions;
  if (winRate      != null) AppState.winRate       = winRate;

  const eqEl  = $('port-equity');
  const pnlEl = $('port-pnl');
  const posEl = $('port-positions');
  const wrEl  = $('port-winrate');

  if (eqEl)  eqEl.textContent  = AppState.equity    != null ? fmtThb(AppState.equity)  : '฿ —';
  if (posEl) posEl.textContent = AppState.openPositions;

  if (pnlEl) {
    const p = AppState.pnlToday;
    if (p == null) { pnlEl.textContent = '—'; pnlEl.className = 'port-value'; }
    else {
      pnlEl.textContent = (p >= 0 ? '+' : '') + fmtThb(p);
      pnlEl.className   = 'port-value ' + (p >= 0 ? 'pnl-positive' : 'pnl-negative');
    }
  }

  if (wrEl) {
    wrEl.textContent = AppState.winRate != null
      ? Number(AppState.winRate).toFixed(1) + '%'
      : '—%';
  }
}

// ═══════════════════════════════════════════════════════════════════
// 5.8  Risk Gauges
// ═══════════════════════════════════════════════════════════════════

function renderRiskGauges({ dailyLossPct, drawdownPct, killSwitch } = {}) {
  if (dailyLossPct != null) AppState.dailyLossPct = clamp(dailyLossPct, 0, 100);
  if (drawdownPct  != null) AppState.drawdownPct  = clamp(drawdownPct,  0, 100);
  if (killSwitch   != null) AppState.killSwitch   = killSwitch;

  const dlFill = $('gauge-daily-loss');
  const dlPct  = $('gauge-daily-loss-pct');
  const ddFill = $('gauge-drawdown');
  const ddPct  = $('gauge-drawdown-pct');
  const kill   = $('kill-indicator');
  const killTx = $('kill-text');

  if (dlFill) dlFill.style.width = AppState.dailyLossPct + '%';
  if (dlPct)  dlPct.textContent  = Math.round(AppState.dailyLossPct) + '%';
  if (ddFill) ddFill.style.width = AppState.drawdownPct + '%';
  if (ddPct)  ddPct.textContent  = Math.round(AppState.drawdownPct)  + '%';

  if (kill) {
    kill.classList.toggle('active', !!AppState.killSwitch);
  }
  if (killTx) killTx.textContent = AppState.killSwitch ? 'KILLED' : 'SAFE';
}

// ═══════════════════════════════════════════════════════════════════
// 5.9  Live Event Feed
// ═══════════════════════════════════════════════════════════════════

const MAX_EVENTS = 100;

function logEvent(msg, kind = 'info') {
  const feed = $('event-feed');
  if (!feed) return;

  const line    = el('div', 'event-line');
  const tsSpan  = el('span', 'ev-ts', new Date().toLocaleTimeString('th-TH', { hour12: false }));
  const typeSpan = el('span', `ev-type ev-${kind}`, kind.toUpperCase());
  const msgSpan  = el('span', `ev-${kind}`, ' ' + msg);

  line.appendChild(tsSpan);
  line.appendChild(typeSpan);
  line.appendChild(msgSpan);

  feed.appendChild(line);
  while (feed.childElementCount > MAX_EVENTS) feed.firstChild.remove();
  // auto-scroll to bottom
  feed.scrollTop = feed.scrollHeight;
}

// ═══════════════════════════════════════════════════════════════════
// 5.10  i18n
// ═══════════════════════════════════════════════════════════════════

const I18N_FALLBACK = {
  en: {
    title: 'Anime Bitcoin Ops Center',
    subtitle: 'BTC/THB Trading System',
    disconnected: 'Disconnected',
    connected: 'Connected',
    emergency_stop: '🛑 EMERGENCY STOP',
    emergency_reset: '↩ RESET',
    simulator: 'SIM',
    live: 'LIVE',
    factory_floor: 'Operations Factory Floor',
    start_all: '▶ Start All',
    stop_all: '■ Stop All',
    price_chart: '📈 Price Chart (Last 100)',
    portfolio: '💼 Portfolio',
    equity: 'Equity',
    pnl_today: 'PnL Today',
    open_positions: 'Positions',
    win_rate: 'Win Rate',
    risk_gauges: '🛡️ Risk Gauges',
    daily_loss: 'Daily Loss',
    drawdown: 'Drawdown',
    kill_switch: 'Kill Switch',
    commander_rank: '👑 Commander Rank',
    level: 'LVL',
    streak: 'Streak:',
    trades: 'Trades:',
    event_feed: '📡 Live Event Feed',
    clear: 'Clear',
  },
  th: {
    title: 'ศูนย์ปฏิบัติการบิทคอยน์',
    subtitle: 'ระบบเทรด BTC/THB',
    disconnected: 'ขาดการเชื่อมต่อ',
    connected: 'เชื่อมต่อแล้ว',
    emergency_stop: '🛑 หยุดฉุกเฉิน',
    emergency_reset: '↩ รีเซ็ต',
    simulator: 'จำลอง',
    live: 'สด',
    factory_floor: 'โรงงานปฏิบัติการ',
    start_all: '▶ เริ่มทั้งหมด',
    stop_all: '■ หยุดทั้งหมด',
    price_chart: '📈 กราฟราคา (100 จุด)',
    portfolio: '💼 พอร์ตโฟลิโอ',
    equity: 'มูลค่า',
    pnl_today: 'กำไร/ขาดทุนวันนี้',
    open_positions: 'ตำแหน่งเปิด',
    win_rate: 'อัตราชนะ',
    risk_gauges: '🛡️ มาตรวัดความเสี่ยง',
    daily_loss: 'ขาดทุนรายวัน',
    drawdown: 'ดรอดาวน์',
    kill_switch: 'สวิตช์หยุด',
    commander_rank: '👑 ยศผู้บัญชาการ',
    level: 'ระดับ',
    streak: 'ต่อเนื่อง:',
    trades: 'เทรด:',
    event_feed: '📡 ฟีดเหตุการณ์สด',
    clear: 'ล้าง',
  },
};

async function loadI18n() {
  try {
    const r = await fetch('/static/i18n.json');
    if (r.ok) {
      const data = await r.json();
      if (data.en) Object.assign(AppState.strings.en, data.en);
      if (data.th) Object.assign(AppState.strings.th, data.th);
    }
  } catch (_) { /* use fallback */ }
  // merge fallbacks
  Object.assign(AppState.strings.en, { ...I18N_FALLBACK.en, ...AppState.strings.en });
  Object.assign(AppState.strings.th, { ...I18N_FALLBACK.th, ...AppState.strings.th });
  applyI18n();
}

function t(key) {
  return AppState.strings[AppState.lang][key] ?? AppState.strings.en[key] ?? key;
}

function applyI18n() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.dataset.i18n;
    el.textContent = t(key);
  });
  // update conn-text live
  const connText = $('conn-text');
  if (connText) connText.textContent = t(AppState.wsConnected ? 'connected' : 'disconnected');
}

function toggleLang() {
  AppState.lang = AppState.lang === 'en' ? 'th' : 'en';
  const btn = $('lang-toggle');
  if (btn) btn.textContent = AppState.lang === 'en' ? 'TH' : 'EN';
  applyI18n();
}

// ═══════════════════════════════════════════════════════════════════
// Agent status rendering
// ═══════════════════════════════════════════════════════════════════

function renderAgents(agentsData) {
  // agentsData: { agent_id: { running: bool, msg_count: int } }
  AppState.agents = agentsData;
  AGENT_DEFS.forEach(def => {
    const info  = agentsData[def.id] ?? { running: false, msg_count: 0 };
    const zone   = $(`zone-${def.id}`);
    const status = $(`status-${def.id}`);
    const msgs   = $(`msgs-${def.id}`);

    if (zone) {
      zone.classList.toggle('running', !!info.running);
      zone.classList.toggle('stopped', !info.running);
    }
    if (status) {
      status.textContent = info.running ? 'RUNNING' : 'STOPPED';
      status.className   = 'chibi-status ' + (info.running ? 'running' : 'stopped');
    }
    if (msgs) msgs.textContent = `msgs: ${info.msg_count ?? 0}`;
  });
}

// ═══════════════════════════════════════════════════════════════════
// Connection status
// ═══════════════════════════════════════════════════════════════════

AppState.wsConnected = false;

function setConnStatus(ok) {
  AppState.wsConnected = ok;
  const led  = $('conn-led');
  const text = $('conn-text');
  if (led)  led.className  = ok ? 'led led-green' : 'led led-red';
  if (text) text.textContent = t(ok ? 'connected' : 'disconnected');
}

// ═══════════════════════════════════════════════════════════════════
// WebSocket — with exponential backoff
// ═══════════════════════════════════════════════════════════════════

let ws = null;

function handleMessage(raw) {
  let m;
  try { m = JSON.parse(raw); } catch { return; }

  switch (m.type) {
    case 'price': {
      const price = m.price ?? m.data?.price;
      const tsMs  = m.ts_ms ?? m.data?.ts_ms ?? Date.now();
      if (price != null) {
        pushPricePoint(price, tsMs);
        logEvent(`BTC/THB ${fmt.format(Number(price))}`, 'price');
      }
      break;
    }
    case 'status': {
      const d = m.data ?? m;
      if (d.market_mode) setMarketMode(d.market_mode);
      if (d.agents)      renderAgents(d.agents);

      // portfolio / risk fields (if present in status)
      if (d.equity          != null) renderPortfolio({ equity: d.equity });
      if (d.pnl_today       != null) renderPortfolio({ pnlToday: d.pnl_today });
      if (d.open_positions  != null) renderPortfolio({ openPositions: d.open_positions });
      if (d.win_rate        != null) renderPortfolio({ winRate: d.win_rate });
      if (d.daily_loss_pct  != null) renderRiskGauges({ dailyLossPct: d.daily_loss_pct });
      if (d.drawdown_pct    != null) renderRiskGauges({ drawdownPct: d.drawdown_pct });
      if (d.kill_switch     != null) renderRiskGauges({ killSwitch: d.kill_switch });

      // uptime / msg_rate in header meta
      const meta = $('price-meta');
      if (meta && d.uptime != null) {
        meta.textContent = `uptime ${d.uptime}s  ·  ${Number(d.msg_rate ?? 0).toFixed(1)} msg/s  ·  lat ${d.latency_ms ?? '?'} ms`;
      }

      // emergency stop UI
      const stopBtn  = $('emergency-stop');
      const resetBtn = $('emergency-reset');
      if (d.emergency_stopped) {
        if (stopBtn)  stopBtn.textContent = t('emergency_stop').replace('EMERGENCY STOP', 'STOPPED');
        if (resetBtn) resetBtn.classList.remove('hidden');
      } else {
        if (stopBtn)  stopBtn.textContent = t('emergency_stop');
        if (resetBtn) resetBtn.classList.add('hidden');
      }
      break;
    }
    case 'signal': {
      logEvent(m.message ?? JSON.stringify(m), 'signal');
      break;
    }
    case 'trade': {
      const isWin = (m.pnl ?? 0) > 0;
      logEvent(`Trade ${m.side ?? ''} @ ${m.price ?? '?'} pnl=${m.pnl ?? '?'}`, 'trade');
      recordTrade(isWin);
      break;
    }
    case 'risk': {
      logEvent(m.message ?? JSON.stringify(m), 'risk');
      break;
    }
    case 'error': {
      logEvent(m.message ?? JSON.stringify(m), 'error');
      break;
    }
    default:
      logEvent(JSON.stringify(m).slice(0, 120), 'info');
  }
}

function connect() {
  if (ws) { try { ws.close(); } catch (_) {} }
  ws = new WebSocket(`ws://${location.host}/ws`);

  ws.onopen = () => {
    setConnStatus(true);
    logEvent('WebSocket connected', 'ok');
    AppState.wsRetryDelay = 1000; // reset backoff
  };

  ws.onmessage = (ev) => handleMessage(ev.data);

  ws.onerror = () => logEvent('WebSocket error', 'error');

  ws.onclose = () => {
    setConnStatus(false);
    const delay = AppState.wsRetryDelay;
    logEvent(`WebSocket closed — reconnecting in ${(delay/1000).toFixed(0)}s…`, 'warn');
    // exponential backoff: 1s, 2s, 4s, 8s … max 30s
    AppState.wsRetryDelay = Math.min(delay * 2, 30000);
    AppState.wsRetryTimer = setTimeout(connect, delay);
  };
}

// ═══════════════════════════════════════════════════════════════════
// API calls
// ═══════════════════════════════════════════════════════════════════

async function apiCall(method, path) {
  try {
    const r = await fetch(path, { method });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    logEvent(`${method} ${path} OK`, 'ok');
    return await r.json().catch(() => null);
  } catch (e) {
    logEvent(`${method} ${path} FAILED: ${e.message}`, 'error');
  }
}

// ═══════════════════════════════════════════════════════════════════
// Event delegation — all clicks
// ═══════════════════════════════════════════════════════════════════

document.addEventListener('click', async (e) => {
  const target = e.target.closest('button') ?? e.target;

  if (target.id === 'emergency-stop') {
    await apiCall('POST', '/api/emergency_stop');
    logEvent('EMERGENCY STOP triggered', 'error');
    return;
  }
  if (target.id === 'emergency-reset') {
    await apiCall('POST', '/api/emergency_reset');
    logEvent('Emergency reset — system ready', 'ok');
    return;
  }
  if (target.id === 'start-all') {
    await apiCall('POST', '/api/agents/start_all');
    logEvent('All agents started', 'ok');
    return;
  }
  if (target.id === 'stop-all') {
    await apiCall('POST', '/api/agents/stop_all');
    logEvent('All agents stopped', 'warn');
    return;
  }
  if (target.id === 'clear-log') {
    const feed = $('event-feed');
    if (feed) while (feed.firstChild) feed.removeChild(feed.firstChild);
    return;
  }
  if (target.id === 'lang-toggle') {
    toggleLang();
    return;
  }
  if (target.dataset.mode) {
    await apiCall('POST', `/api/switch_mode?mode=${encodeURIComponent(target.dataset.mode)}`);
    return;
  }
});

// ═══════════════════════════════════════════════════════════════════
// Bootstrap
// ═══════════════════════════════════════════════════════════════════

async function init() {
  initAgentGrid();
  initChart();
  renderGamification();
  renderPortfolio();
  renderRiskGauges();
  await loadI18n();

  // try to fetch initial status via REST
  try {
    const r = await fetch('/api/status');
    if (r.ok) {
      const data = await r.json();
      handleMessage(JSON.stringify({ type: 'status', ...data }));
    }
  } catch (_) {}

  connect();
  logEvent('Anime Bitcoin Ops Center initialised', 'ok');
}

document.addEventListener('DOMContentLoaded', init);
