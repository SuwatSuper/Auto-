/* CEO Character — living chibi CEO overlay for Kingdom Prime dashboard */
(function () {
  'use strict';

  // ── Safety guard: abort silently if dashboard globals are missing ──────
  try {
    if (typeof buildChibiSVG === 'undefined' ||
        typeof EMOTION_MAP   === 'undefined' ||
        typeof getEmotion    === 'undefined' ||
        typeof AGENTS        === 'undefined' ||
        typeof State         === 'undefined') {
      console.warn('[CEO] Dashboard globals not ready — CEO character disabled');
      return;
    }
  } catch (e) {
    console.warn('[CEO] Init guard error:', e);
    return;
  }

  // ── A) Deterministic PRNG ──────────────────────────────────────────────
  function mulberry32(seed){return function(){let t=seed+=0x6D2B79F5;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return((t^t>>>14)>>>0)/4294967296;}}
  const rng = mulberry32(Date.now()>>>0); // animation-only randomness; NEVER used for displayed data

  // ── CEO definition ─────────────────────────────────────────────────────
  const CEO_DEF = { hairColor: '#f5f5f5', bodyColor: '#1a1a2e', skinColor: '#fde68a', accessory: 'crown' };

  // ── H) Idle grumble lines ──────────────────────────────────────────────
  const CEO_IDLE = {
    neutral:     ["ตรวจงานตามปกติ...","ทุกอย่างเรียบร้อยดีนะ"],
    happy:       ["วันนี้อารมณ์ดีเป็นพิเศษ!","งานราบรื่นแบบนี้สิที่ชอบ"],
    ecstatic:    ["สุดยอดไปเลยทีมเรา!!","นี่แหละอาณาจักรของเรา!"],
    excited:     ["มีอะไรน่าตื่นเต้นแน่ ๆ!","กราฟขยับแล้ว ๆ!"],
    confident:   ["เชื่อมือทีมนี้ได้เลย","แผนเราต้องเวิร์กแน่นอน"],
    satisfied:   ["พอใจ ๆ ผลงานใช้ได้","แบบนี้แหละที่ต้องการ"],
    calm:        ["ใจเย็น ๆ ค่อยเป็นค่อยไป","ตลาดนิ่ง เราก็นิ่ง"],
    determined:  ["วันนี้ต้องทำให้ดีกว่าเมื่อวาน","ลุยต่อ ห้ามหยุด"],
    focused:     ["อย่าเพิ่งกวนนะ กำลังดูกราฟ","โฟกัส ๆ ตัวเลขสำคัญทั้งนั้น"],
    curious:     ["เอ๊ะ ตัวเลขนี้มันแปลก ๆ","ขอดูข้อมูลหน่อยซิ..."],
    cautious:    ["ช้า ๆ ได้พร้าเล่มงาม","อย่าเพิ่งรีบ ดูให้รอบคอบ"],
    anxious:     ["ใจคอไม่ดีเลยแฮะ...","เช็คความเสี่ยงอีกรอบซิ"],
    stressed:    ["งานเข้าอีกแล้ว...","ขอกาแฟแก้วที่สามหน่อย"],
    tired:       ["เหนื่อย... แต่ต้องไหว","ขอพักสายตาแป๊บนึง"],
    worried:     ["ราคาแบบนี้ไม่ค่อยสบายใจ","Risk! ดูแลให้ดีนะ"],
    frustrated:  ["ทำไมมันเป็นแบบนี้เนี่ย!","บ่นแล้วนะ บ่นจริง ๆ ด้วย!"],
    overwhelmed: ["งานถาโถมมากไปแล้ว...","ทีละอย่าง ๆ ใจเย็น CEO"],
    panicked:    ["ทุกหน่วยเตรียมพร้อมด่วน!!","นี่มันสถานการณ์ฉุกเฉิน!"],
    angry:       ["ใครรับผิดชอบเรื่องนี้!!","ยอมรับไม่ได้เด็ดขาด!"],
    sleeping:    ["Zzz... กราฟ... เขียว...","ตีสองแล้วเหรอเนี่ย... Zzz"]
  };

  // ── I) Commands to agents ──────────────────────────────────────────────
  const CEO_COMMANDS = {
    market_analyst:    "Market Analyst! BTC ตอนนี้ {price} บาท ({chg5}% ใน 5 นาที) วิเคราะห์ด่วน!",
    news_intelligence: "News! มีข่าวอะไรทำราคาขยับ {chg1}% รึเปล่า เช็คซิ",
    risk_management:   "Risk! คุมลิมิตให้แน่น ห้ามพลาดเด็ดขาด",
    probability_lab:   "Probability! โอกาสชนะรอบนี้เท่าไหร่ คำนวณมา",
    research_dept:     "Research! ราคา {price} บาทนี้ เทียบสถิติย้อนหลังให้หน่อย",
    execution_agent:   "Execution! ซ้อมให้คม ค่าธรรมเนียมห้ามตกหล่น",
    supreme_commander: "Commander! สรุปสัญญาณทั้งหมดแล้วตัดสินใจมา",
    paper_trader:      "Trader! พอร์ตกระดาษเป็นไงบ้าง รายงาน!",
    treasury:          "Treasury! เฝ้าเงินสดไว้ให้ดี อนุมัติเฉพาะที่คุ้ม"
  };

  const NO_DATA_LINE = "ยังไม่มีข้อมูลเข้ามา... รอแป๊บนะ";

  // ── B) Build DOM ───────────────────────────────────────────────────────
  const layer = document.createElement('div');
  layer.id = 'ceo-layer';

  const charEl = document.createElement('div');
  charEl.id = 'ceo-char';

  const chibiDiv = document.createElement('div');
  chibiDiv.id = 'ceo-chibi';

  const bubble = document.createElement('div');
  bubble.id = 'ceo-bubble';

  const hand = document.createElement('span');
  hand.id = 'ceo-hand';
  hand.textContent = '👋';

  charEl.appendChild(bubble);
  charEl.appendChild(chibiDiv);
  charEl.appendChild(hand);
  layer.appendChild(charEl);

  // Control buttons
  const controls = document.createElement('div');
  controls.id = 'ceo-controls';

  const btnToggle = document.createElement('button');
  btnToggle.className = 'ceo-btn';
  btnToggle.title = 'Show/hide CEO';
  btnToggle.textContent = '👑';

  const btnVoice = document.createElement('button');
  btnVoice.className = 'ceo-btn';
  btnVoice.title = 'Toggle TTS voice';
  btnVoice.textContent = '🔊';

  controls.appendChild(btnToggle);
  controls.appendChild(btnVoice);
  layer.appendChild(controls);

  document.body.appendChild(layer);

  // ── Persistent settings ────────────────────────────────────────────────
  let ceoVisible = localStorage.getItem('ceo_visible') !== 'false';
  let ttsEnabled = localStorage.getItem('ceo_tts') === 'true';

  function applyCeoVisible() {
    charEl.style.display = ceoVisible ? '' : 'none';
    btnToggle.classList.toggle('ceo-btn-off', !ceoVisible);
  }
  function applyTtsState() {
    btnVoice.classList.toggle('ceo-btn-off', !ttsEnabled);
  }
  applyCeoVisible();
  applyTtsState();

  btnToggle.addEventListener('click', function () {
    ceoVisible = !ceoVisible;
    localStorage.setItem('ceo_visible', ceoVisible);
    applyCeoVisible();
  });
  btnVoice.addEventListener('click', function () {
    ttsEnabled = !ttsEnabled;
    localStorage.setItem('ceo_tts', ttsEnabled);
    applyTtsState();
  });

  // ── State ─────────────────────────────────────────────────────────────
  let currentEmo = 'neutral';
  let posX = 40, posY = 120;
  let facingLeft = false;
  let walking = false;
  let walkResolve = null;
  let walkTimer = null;

  // F) Data state
  const priceBuffer = []; // {price, ts}
  let chg1 = 0, chg5 = 0;
  let wsDown = false;
  let lastApprovedMs = 0, lastVetoedMs = 0, lastVetoReason = '';
  let latestDecisionId = null;

  // Scheduler
  let patrolIndex = 0;
  let nextActionMs = Date.now() + 12000 + rng() * 13000;
  let emergencySaidMs = 0;
  const cooldowns = {}; // event type → last fired ms

  // ── Render chibi ──────────────────────────────────────────────────────
  function renderCeo(emoId) {
    chibiDiv.innerHTML = buildChibiSVG(CEO_DEF, emoId);
  }
  renderCeo(currentEmo);

  // ── C) Movement ───────────────────────────────────────────────────────
  function clamp(val, lo, hi) { return Math.max(lo, Math.min(hi, val)); }

  function walkTo(tx, ty, fast) {
    fast = fast || false;
    const margin = 40, headerY = 90;
    tx = clamp(tx, margin, window.innerWidth  - margin - 96);
    ty = clamp(ty, headerY, window.innerHeight - margin - 96);

    const dx = tx - posX, dy = ty - posY;
    const dist = Math.sqrt(dx * dx + dy * dy);
    const speed = fast ? 260 : 120;
    const duration = dist < 1 ? 0 : Math.round(dist / speed * 1000);

    // Facing direction
    facingLeft = dx < 0;

    charEl.classList.remove('ceo-walking', 'ceo-walking-left');
    if (duration > 100) {
      charEl.classList.add(facingLeft ? 'ceo-walking-left' : 'ceo-walking');
    }

    charEl.style.transition = `left ${duration}ms linear, top ${duration}ms linear`;
    charEl.style.left = tx + 'px';
    charEl.style.top  = ty + 'px';
    posX = tx; posY = ty;
    walking = true;

    if (walkResolve) { walkResolve(); walkResolve = null; }
    if (walkTimer)   { clearTimeout(walkTimer); walkTimer = null; }

    return new Promise(function (resolve) {
      walkResolve = resolve;
      function onEnd() {
        charEl.removeEventListener('transitionend', onEnd);
        charEl.classList.remove('ceo-walking', 'ceo-walking-left');
        walking = false;
        walkResolve = null;
        resolve();
      }
      charEl.addEventListener('transitionend', onEnd);
      walkTimer = setTimeout(function () {
        charEl.classList.remove('ceo-walking', 'ceo-walking-left');
        walking = false;
        walkResolve = null;
        resolve();
      }, duration + 200);
    });
  }

  function walkToAgent(agentId) {
    const el = document.getElementById('agent-card-' + agentId);
    if (!el) return wander();
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.bottom < 0 || rect.top > window.innerHeight) return wander();
    const leftX  = rect.left - 110;
    const rightX = rect.right + 14;
    const ty = rect.top + rect.height - 110;
    const tx = (leftX >= 40) ? leftX : rightX;
    return walkTo(tx, ty, false);
  }

  function wander() {
    const tx = 40 + rng() * (window.innerWidth  - 180);
    const ty = 90 + rng() * (window.innerHeight - 200);
    return walkTo(tx, ty, false);
  }

  // ── D) Speech ─────────────────────────────────────────────────────────
  let bubbleTimer = null;
  function say(text) {
    bubble.textContent = text;
    bubble.style.display = 'block';
    if (bubbleTimer) clearTimeout(bubbleTimer);
    const dur = Math.max(2500, text.length * 70);
    bubbleTimer = setTimeout(function () {
      bubble.style.display = 'none';
    }, dur);

    if (ttsEnabled && typeof speechSynthesis !== 'undefined') {
      try {
        speechSynthesis.cancel();
        const utter = new SpeechSynthesisUtterance(text);
        utter.lang = 'th-TH';
        utter.rate = 1.05;
        const voices = speechSynthesis.getVoices();
        const thVoice = voices.find(function (v) {
          return v.lang && v.lang.toLowerCase().startsWith('th');
        }) || null;
        utter.voice = thVoice;
        speechSynthesis.speak(utter);
      } catch (e) { /* TTS is best-effort */ }
    }
  }

  // ── E) Wave ───────────────────────────────────────────────────────────
  function wave() {
    hand.style.display = 'inline';
    hand.classList.remove('ceo-waving');
    void hand.offsetWidth; // reflow
    hand.classList.add('ceo-waving');
    setTimeout(function () {
      hand.classList.remove('ceo-waving');
      hand.style.display = 'none';
    }, 2000);
  }

  // ── F) Data polling ───────────────────────────────────────────────────
  function tickPrices() {
    try {
      // SYMBOL_PRICES is populated by handlePrice() in kingdom.html
      const price = SYMBOL_PRICES['thb_btc'] || SYMBOL_PRICES['THB_BTC'] ||
                    (Object.values(SYMBOL_PRICES)[0]) || null;
      if (price != null) {
        const now = Date.now();
        priceBuffer.push({ price: Number(price), ts: now });
        // Keep max 600 entries
        while (priceBuffer.length > 600) priceBuffer.shift();

        // Compute chg1 (60s) and chg5 (300s)
        const cutoff1 = now - 60000, cutoff5 = now - 300000;
        const old1 = priceBuffer.find(function (p) { return p.ts >= cutoff1; });
        const old5 = priceBuffer.find(function (p) { return p.ts >= cutoff5; });
        const cur  = priceBuffer[priceBuffer.length - 1].price;
        chg1 = old1 ? ((cur - old1.price) / old1.price * 100) : 0;
        chg5 = old5 ? ((cur - old5.price) / old5.price * 100) : 0;
      }
    } catch (e) { /* non-critical */ }
  }

  async function pollAudit() {
    try {
      const resp = await fetch('/api/ceo/audit?limit=5');
      if (!resp.ok) return;
      const data = await resp.json();
      const decisions = data.decisions || data.recent || [];
      if (decisions.length > 0) {
        const newest = decisions[0];
        const newId = newest.decision_id || newest.id || JSON.stringify(newest).slice(0, 40);
        if (latestDecisionId !== null && newId !== latestDecisionId) {
          const outcome = newest.outcome || newest.decision || '';
          if (outcome === 'EXECUTE' || outcome === 'approved') {
            triggerEvent('approved', { symbol: newest.symbol });
          } else if (outcome === 'HOLD' || outcome === 'vetoed' || outcome === 'VETOED' ||
                     (newest.reasons && newest.reasons.length > 0)) {
            triggerEvent('vetoed', { reason: (newest.reasons || []).join(', '), symbol: newest.symbol });
          }
        }
        latestDecisionId = newId;
      }
    } catch (e) { /* non-critical */ }
  }

  async function pollHealth() {
    try {
      const resp = await fetch('/healthz');
      wsDown = !resp.ok;
    } catch (e) {
      wsDown = true;
    }
  }

  // ── G) Emotion engine ─────────────────────────────────────────────────
  function computeEmotion() {
    try {
      const now = Date.now();
      const emergency = !!(State.killSwitch);
      const runningCount = AGENTS.filter(function (a) {
        return !(State.agents[a.id] && State.agents[a.id].running === false);
      }).length;
      const vetoAgeSec     = lastVetoedMs   ? (now - lastVetoedMs)   / 1000 : 9999;
      const approvedAgeSec = lastApprovedMs ? (now - lastApprovedMs) / 1000 : 9999;
      const uptimeMinutes  = (State.uptimeSeconds || 0) / 60;
      const hour = new Date().getHours();

      const stress = clamp(
        15 + Math.max(0, -chg1) * 60 + Math.max(0, -chg5) * 15 +
        (emergency ? 75 : 0) + (wsDown ? 35 : 0) + (vetoAgeSec < 60 ? 25 : 0),
        0, 100
      );
      const morale = clamp(
        70 + chg5 * 12 + (approvedAgeSec < 120 ? 15 : 0) -
        (AGENTS.length - runningCount) * 12 - (emergency ? 40 : 0),
        0, 100
      );
      const fatigue = clamp(
        20 + (hour < 6 ? 55 : hour >= 22 ? 30 : 0) + uptimeMinutes / 30,
        0, 100
      );
      const confidence = clamp(
        55 + (runningCount / AGENTS.length) * 35 + chg5 * 8 - (wsDown ? 25 : 0),
        0, 100
      );

      const emoId = getEmotion({ morale, stress, fatigue, confidence });
      if (emoId !== currentEmo) {
        currentEmo = emoId;
        renderCeo(currentEmo);
      }
    } catch (e) { /* non-critical */ }
  }

  // ── Price / command formatter ──────────────────────────────────────────
  function fmtPrice() {
    const price = SYMBOL_PRICES['thb_btc'] || SYMBOL_PRICES['THB_BTC'] ||
                  (Object.values(SYMBOL_PRICES)[0]) || null;
    if (price == null) return null;
    return Number(price).toLocaleString('th-TH');
  }

  function fmtChg(val) {
    const sign = val >= 0 ? '+' : '';
    return sign + val.toFixed(2);
  }

  function buildCommand(agentId) {
    const tpl = CEO_COMMANDS[agentId];
    if (!tpl) return NO_DATA_LINE;
    const price = fmtPrice();
    if (price == null) return NO_DATA_LINE;
    return tpl
      .replace('{price}', price)
      .replace('{chg1}',  fmtChg(chg1))
      .replace('{chg5}',  fmtChg(chg5));
  }

  // ── J) Event interrupts ───────────────────────────────────────────────
  const EVENT_COOLDOWN_MS = 8000;

  function canFire(type) {
    const now = Date.now();
    if ((now - (cooldowns[type] || 0)) < EVENT_COOLDOWN_MS) return false;
    cooldowns[type] = now;
    return true;
  }

  function triggerEvent(type, data) {
    data = data || {};
    if (!canFire(type)) return;
    if (type === 'approved') {
      lastApprovedMs = Date.now();
      walkToAgent('supreme_commander').then(function () {
        wave();
        say("อนุมัติแล้ว! เดินหน้าตามแผน 💪");
      });
    } else if (type === 'vetoed') {
      lastVetoedMs = Date.now();
      lastVetoReason = data.reason || '';
      const msg = "Veto! ดีมากที่กันไว้" + (lastVetoReason ? ': ' + lastVetoReason : '');
      walkToAgent('risk_management').then(function () { say(msg); });
    } else if (type === 'priceUp') {
      say("ขึ้นแรงมาก! ทุกคนตามให้ทัน!");
    } else if (type === 'priceDown') {
      walkToAgent('risk_management').then(function () {
        say("ดิ่งแล้ว! Risk เตรียมรับมือ!");
      });
    } else if (type === 'wsDown') {
      say("สัญญาณหลุด! ขาดการติดต่อ ขอข้อมูลด่วน");
    }
  }

  // ── K) Scheduler ─────────────────────────────────────────────────────
  function scheduleNext() {
    nextActionMs = Date.now() + 12000 + rng() * 13000;
  }

  function doScheduledAction() {
    const r = rng();
    if (r < 0.55) {
      // Patrol: walk to next agent in round-robin
      const agent = AGENTS[patrolIndex % AGENTS.length];
      patrolIndex++;
      walkToAgent(agent.id).then(function () {
        wave();
        say(buildCommand(agent.id));
      });
    } else if (r < 0.85) {
      // Wander + idle grumble
      wander().then(function () {
        const lines = CEO_IDLE[currentEmo] || CEO_IDLE['neutral'];
        const line = lines[Math.floor(rng() * lines.length)];
        say(line);
      });
    } else {
      // Wave in place
      wave();
    }
    scheduleNext();
  }

  // ── Main tick (1s) ────────────────────────────────────────────────────
  let lastWsDown = false;
  let slowTick = 0;

  function tick() {
    if (document.hidden) return;
    if (!ceoVisible) return;

    const now = Date.now();

    // Price buffer
    tickPrices();

    // Slow ticks (every 5 iterations = 5s)
    slowTick++;
    if (slowTick >= 5) {
      slowTick = 0;
      computeEmotion();
    }

    // Emergency check
    try {
      const emergency = !!(State.killSwitch);
      if (emergency && canFire('emergency') && (now - emergencySaidMs) > 30000) {
        emergencySaidMs = now;
        walkTo(window.innerWidth / 2 - 48, window.innerHeight / 2 - 48, true).then(function () {
          say("หยุดทุกอย่างเดี๋ยวนี้!! รอคำสั่งมนุษย์เท่านั้น");
        });
      }
    } catch (e) { /* non-critical */ }

    // WS down event
    if (wsDown && !lastWsDown) {
      triggerEvent('wsDown', {});
    }
    lastWsDown = wsDown;

    // Price move interrupts
    if (Math.abs(chg1) > 0.5 && priceBuffer.length > 5) {
      if (chg1 > 0.5 && canFire('priceUp'))   triggerEvent('priceUp', {});
      if (chg1 < -0.5 && canFire('priceDown')) triggerEvent('priceDown', {});
    }

    // Scheduled action
    if (now >= nextActionMs) {
      doScheduledAction();
    }
  }

  // ── Init ─────────────────────────────────────────────────────────────
  // Greet on load
  setTimeout(function () {
    wave();
    say("สวัสดีครับ! CEO ประจำการแล้ว 👋");
    scheduleNext();
  }, 1500);

  // Slow polling: audit + health every 10s
  setInterval(function () {
    pollAudit();
    pollHealth();
  }, 10000);
  pollHealth(); // immediate first check

  // Main tick every 1s
  setInterval(tick, 1000);

  // TTS voices load async in some browsers
  if (typeof speechSynthesis !== 'undefined') {
    speechSynthesis.onvoiceschanged = function () { /* voices now available */ };
  }

})();
