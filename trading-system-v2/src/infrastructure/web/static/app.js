const $ = (id) => document.getElementById(id);
const fmt = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const MAX_POINTS = 300;

let ws = null;
const priceData = [];

const chart = new Chart($('chart').getContext('2d'), {
  type: 'line',
  data: {
    labels: [],
    datasets: [{
      label: 'THB_BTC',
      data: [],
      borderColor: '#34d399',
      backgroundColor: 'rgba(52,211,153,0.1)',
      borderWidth: 2,
      tension: 0.2,
      pointRadius: 0,
      fill: true,
    }],
  },
  options: {
    responsive: true,
    animation: false,
    scales: {
      x: { ticks: { color: '#64748b', maxTicksLimit: 6 }, grid: { color: '#1e293b' } },
      y: { ticks: { color: '#64748b', callback: (v) => fmt.format(v) }, grid: { color: '#1e293b' } },
    },
    plugins: { legend: { display: false } },
  },
});

function logEvent(msg, kind = 'info') {
  const el = $('events');
  const line = document.createElement('div');
  line.className = `event-${kind}`;
  const t = new Date().toLocaleTimeString();
  line.textContent = `[${t}] ${msg}`;
  el.prepend(line);
  while (el.childElementCount > 200) el.lastChild.remove();
}

function setConn(ok) {
  $('conn-led').className = `led ${ok ? 'led-green' : 'led-red'}`;
  $('conn-text').textContent = ok ? 'Connected' : 'Disconnected';
}

function renderStatus(s) {
  $('mode').textContent = s.mode;
  $('uptime').textContent = `${s.uptime_sec}s`;
  $('msg-rate').textContent = s.msg_per_sec.toFixed(1);
  $('latency').textContent = `${s.latency_ms} ms`;
  if (s.latest_price != null) {
    $('price').textContent = fmt.format(Number(s.latest_price));
  }
  const wrap = $('agents');
  wrap.innerHTML = '';
  s.agents.forEach((a) => {
    const row = document.createElement('div');
    row.className = 'flex items-center justify-between bg-slate-900 rounded px-3 py-2';
    row.innerHTML = `
      <div>
        <div class="flex items-center gap-2">
          <span class="led ${a.running ? 'led-green' : 'led-red'}"></span>
          <span class="font-semibold">${a.name}</span>
        </div>
        <div class="text-xs text-slate-500 font-mono">msgs: ${a.msg_count} · last: ${a.latest_price ?? '—'}</div>
      </div>
      <div class="flex gap-1">
        <button data-act="start" data-name="${a.name}" class="bg-green-700 hover:bg-green-600 py-1 px-2 rounded text-xs">Start</button>
        <button data-act="stop"  data-name="${a.name}" class="bg-yellow-700 hover:bg-yellow-600 py-1 px-2 rounded text-xs">Stop</button>
      </div>`;
    wrap.appendChild(row);
  });
  if (s.emergency_stopped) {
    $('emergency-stop').textContent = '🛑 STOPPED — Click to clear';
  }
}

function pushPricePoint(p) {
  const ts = new Date(p.ts_ms).toLocaleTimeString();
  priceData.push({ t: ts, v: Number(p.price) });
  if (priceData.length > MAX_POINTS) priceData.shift();
  chart.data.labels = priceData.map((d) => d.t);
  chart.data.datasets[0].data = priceData.map((d) => d.v);
  chart.update('none');
  $('price').textContent = fmt.format(Number(p.price));
  $('price-meta').textContent = `Last update: ${ts} · event_id ${p.event_id.slice(0, 8)}`;
}

async function api(method, path) {
  try {
    const r = await fetch(path, { method });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    logEvent(`${method} ${path} OK`, 'ok');
    return await r.json();
  } catch (e) {
    logEvent(`${method} ${path} FAIL: ${e.message}`, 'error');
  }
}

function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => { setConn(true); logEvent('WebSocket connected', 'ok'); };
  ws.onclose = () => {
    setConn(false);
    logEvent('WebSocket disconnected, retrying in 2s…', 'warn');
    setTimeout(connect, 2000);
  };
  ws.onerror = () => logEvent('WebSocket error', 'error');
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === 'price') pushPricePoint(m.data);
    else if (m.type === 'status') renderStatus(m.data);
  };
}

document.addEventListener('click', async (e) => {
  const t = e.target;
  if (t.id === 'emergency-stop') {
    await api('POST', '/api/emergency_stop');
    logEvent('EMERGENCY STOP triggered', 'error');
    return;
  }
  if (t.id === 'start-all') { await api('POST', '/api/agents/start_all'); return; }
  if (t.id === 'stop-all') { await api('POST', '/api/agents/stop_all'); return; }
  if (t.id === 'clear-log') { $('events').innerHTML = ''; return; }
  if (t.dataset.mode) { await api('POST', `/api/mode/${t.dataset.mode}`); return; }
  if (t.dataset.act && t.dataset.name) {
    await api('POST', `/api/agents/${t.dataset.name}/${t.dataset.act}`);
    return;
  }
});

fetch('/api/status').then((r) => r.json()).then(renderStatus).catch(() => {});
connect();
