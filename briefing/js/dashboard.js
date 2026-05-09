/* desktop-brief — fullscreen dashboard.
 * Pulls JSON from the daemon's localhost server (127.0.0.1:8766) and renders.
 */

const STATE_BASE = 'http://127.0.0.1:8766';
const SOURCES = [
  'email', 'calendar', 'weather', 'stocks',
  'hardware', 'news_headlines', 'news_hottake', 'grants', 'health',
];
const POLL_MS = 5000;

const $ = (id) => document.getElementById(id);

async function fetchSource(name) {
  try {
    const r = await fetch(`${STATE_BASE}/${name}.json`, { cache: 'no-store' });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  }
}

/* ----- formatters ----- */
function fmtPct(n) {
  if (n === null || n === undefined) return '—';
  const sign = n >= 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
}
function fmtPrice(n) {
  if (n === null || n === undefined) return '—';
  return n >= 1000 ? n.toLocaleString(undefined, { maximumFractionDigits: 0 })
                   : n.toFixed(2);
}
function fmtUptime(s) {
  if (!s) return '—';
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `up ${d}d ${h}h`;
  if (h) return `up ${h}h ${m}m`;
  return `up ${m}m`;
}
function fmtMins(m) {
  if (m === null || m === undefined) return '—';
  if (m < 60) return `in ${m} min`;
  return `in ${Math.floor(m / 60)}h ${m % 60}m`;
}
function timeOfIso(iso) {
  if (!iso) return '';
  return iso.slice(11, 16);
}

/* ----- clock (tick every second locally) ----- */
function tickClock() {
  const now = new Date();
  const h = String(now.getHours()).padStart(2, '0');
  const m = String(now.getMinutes()).padStart(2, '0');
  const s = String(now.getSeconds()).padStart(2, '0');
  $('clock-time').textContent = `${h}:${m}:${s}`;
  $('clock-date').textContent = now.toDateString().toUpperCase();
}
setInterval(tickClock, 1000);
tickClock();

/* ----- email ----- */
function renderEmail(doc) {
  if (!doc) return;
  const d = doc.data || {};
  $('email-unread').textContent = d.unread_24h_count ?? '—';
  $('email-starred').textContent = d.starred_count ?? '—';
  const list = $('email-list');
  list.innerHTML = '';
  if (!d.available) {
    list.innerHTML = `<li class="dim">unavailable: ${d.reason || 'thunderbird offline'}</li>`;
    return;
  }
  const all = (d.starred || []).map(m => ({ ...m, _starred: true }))
              .concat((d.top_unread || []).filter(m => !(d.starred || []).find(s => s.id === m.id)));
  for (const m of all.slice(0, 18)) {
    const li = document.createElement('li');
    const sender = (m.from || '').split('<')[0].trim() || '(unknown)';
    li.innerHTML = `
      <span class="row-meta">${m._starred ? '<span class="accent-warm">★</span>' : ' '} </span>
      <span class="row-title"><b>${escapeHtml(sender.slice(0, 24))}</b> — ${escapeHtml(m.subject || '(no subject)')}</span>
    `;
    li.title = `${m.from} · ${m.subject}\n${(m.preview || '').slice(0, 200)}`;
    li.addEventListener('click', () => openEmail(m));
    list.appendChild(li);
  }
}

function openEmail(m) {
  // Best-effort: use the mid:<id> URI Thunderbird supports, falling back to Thunderbird default action.
  const id = m.id || m.messageId;
  if (id) window.open(`mid:${id}`, '_blank');
}

/* ----- calendar ----- */
function renderCalendar(doc) {
  if (!doc) return;
  const d = doc.data || {};
  if (!d.available) {
    $('calendar-next-title').textContent = 'unavailable';
    $('calendar-next-when').textContent = d.reason || '';
    return;
  }
  const next = d.next_event;
  $('calendar-next-title').textContent = next ? next.title : 'no upcoming event';
  $('calendar-next-when').textContent = next ? `${timeOfIso(next.start)} · ${fmtMins(d.minutes_until_next)}${next.location ? ' · ' + next.location : ''}` : '—';

  const renderList = (events, ulId) => {
    const ul = $(ulId);
    ul.innerHTML = '';
    for (const ev of (events || []).slice(0, 8)) {
      const li = document.createElement('li');
      li.innerHTML = `<span class="row-meta">${timeOfIso(ev.start)}</span>
                      <span class="row-title">${escapeHtml(ev.title)}</span>`;
      li.title = ev.location ? `${ev.title} · ${ev.location}` : ev.title;
      ul.appendChild(li);
    }
    if (!events || events.length === 0) {
      ul.innerHTML = '<li class="dim">— no events —</li>';
    }
  };
  renderList(d.today, 'calendar-today');
  renderList(d.tomorrow, 'calendar-tomorrow');
}

/* ----- stocks ----- */
function renderStocks(doc) {
  if (!doc) return;
  const d = doc.data || {};
  $('market-state').textContent = `MARKET ${d.market_state || '?'}`;
  $('stocks-meta').textContent = d.as_of ? `as of ${d.as_of.slice(11, 16)} UTC` : '—';

  const renderRow = (q) => {
    const pct = q.change_pct;
    const cls = pct >= 0 ? 'up' : 'down';
    const arrow = pct >= 0 ? '▲' : '▼';
    return `<li>
      <span class="sym">${q.symbol.replace('^', '')}</span>
      <span class="name">${escapeHtml(q.name || '')}</span>
      <span class="price">${fmtPrice(q.price)}</span>
      <span class="pct ${cls}">${arrow} ${fmtPct(pct)}</span>
    </li>`;
  };

  $('stocks-indices').innerHTML = (d.indices || []).map(renderRow).join('') || '<li class="dim">—</li>';
  const watch = (d.watchlist || []).slice().sort((a, b) => Math.abs((b.change_pct||0)) - Math.abs((a.change_pct||0)));
  $('stocks-watch').innerHTML = watch.map(renderRow).join('') || '<li class="dim">—</li>';

  // Click = open Yahoo Finance chart
  for (const li of $('stocks-watch').children) {
    const sym = li.querySelector('.sym').textContent;
    li.addEventListener('click', () => window.open(`https://finance.yahoo.com/quote/${encodeURIComponent(sym)}`, '_blank'));
  }
}

/* ----- weather ----- */
function renderWeather(doc) {
  if (!doc) return;
  const d = doc.data || {};
  const cur = d.current || {};
  const today = d.today || {};
  $('weather-icon').textContent = cur.icon || '🌡';
  $('weather-temp').textContent = `${cur.temp_f ?? '—'}°`;
  $('weather-cond').textContent = cur.condition || '—';
  $('weather-meta').textContent = `hi ${today.high_f ?? '—'}° / lo ${today.low_f ?? '—'}° · ${today.precip_chance ?? 0}% precip · 💧 ${cur.humidity ?? '—'}% · 🌬 ${cur.wind_mph ?? '—'} mph ${cur.wind_dir ?? ''}`;
  $('weather-loc').textContent = (d.location || 'NORMAN, OK').toUpperCase();
}

/* ----- hardware ----- */
const ARC_CIRC = 2 * Math.PI * 34; // r=34 in svg

function setGauge(arcId, pct) {
  const arc = $(arcId);
  if (!arc) return;
  const p = Math.max(0, Math.min(100, pct || 0));
  arc.style.strokeDashoffset = String(ARC_CIRC * (1 - p / 100));
  arc.classList.remove('warn', 'crit');
  if (p > 90) arc.classList.add('crit');
  else if (p > 75) arc.classList.add('warn');
}

function renderHardware(doc) {
  if (!doc) return;
  const d = doc.data || {};
  const cpu = d.cpu || {}, mem = d.memory || {}, disk = d.disk || {}, net = d.network || {};
  $('gauge-cpu').textContent = (cpu.overall_pct ?? 0).toFixed(0);
  $('gauge-mem').textContent = (mem.pct ?? 0).toFixed(0);
  $('gauge-disk').textContent = (disk.pct ?? 0).toFixed(0);
  setGauge('gauge-cpu-arc', cpu.overall_pct);
  setGauge('gauge-mem-arc', mem.pct);
  setGauge('gauge-disk-arc', disk.pct);
  $('hw-temp').textContent = cpu.temp_c != null ? `${cpu.temp_c}°C CPU` : '— temp';
  $('hw-net').textContent = `↓${(net.rx_kbps||0).toFixed(0)} ↑${(net.tx_kbps||0).toFixed(0)} kb/s`;
  $('hw-load').textContent = `load ${(cpu.load_avg || []).map(n => n.toFixed(2)).join(' / ')}`;
  $('hardware-uptime').textContent = fmtUptime(d.uptime_s);
}

/* ----- news ----- */
function renderNews(headlinesDoc, hottakeDoc) {
  if (hottakeDoc) {
    $('news-take').innerHTML = simpleMarkdown(hottakeDoc.data?.summary_markdown || '—');
  } else if (headlinesDoc) {
    $('news-take').innerHTML = '<div class="dim">hot take pending — generated daily</div>';
  } else {
    $('news-take').innerHTML = '<div class="dim">no news yet</div>';
  }
  $('news-meta').textContent = headlinesDoc ? `${(headlinesDoc.data?.headlines || []).length} headlines` : '—';

  const list = $('news-list');
  list.innerHTML = '';
  for (const h of (headlinesDoc?.data?.headlines || []).slice(0, 18)) {
    const li = document.createElement('li');
    li.innerHTML = `<span class="row-meta">[${escapeHtml((h.category || '?').slice(0,5))}]</span>
                    <span class="row-title">${escapeHtml(h.title || '')} <span class="dim">— ${escapeHtml(h.source || '')}</span></span>`;
    if (h.url) li.addEventListener('click', () => window.open(h.url, '_blank'));
    list.appendChild(li);
  }
}

/* ----- grants ----- */
function renderGrants(doc) {
  if (!doc) return;
  const opps = doc.data?.opportunities || [];
  $('grants-meta').textContent = opps.length ? `${opps.length} open · next in ${opps[0].days_until_deadline}d` : 'none open';
  const list = $('grants-list');
  list.innerHTML = '';
  for (const o of opps.slice(0, 12)) {
    const li = document.createElement('li');
    const urgency = o.days_until_deadline < 14 ? 'down' : o.days_until_deadline < 30 ? 'accent-warm' : '';
    li.innerHTML = `<span class="row-meta ${urgency}">${o.deadline} · ${o.days_until_deadline}d</span>
                    <span class="row-title"><b>${escapeHtml(o.agency)}</b> — ${escapeHtml(o.topic)}</span>`;
    li.title = `${o.program} ${o.phase ? '· ' + o.phase : ''}\n${o.summary || ''}`;
    if (o.url) li.addEventListener('click', () => window.open(o.url, '_blank'));
    list.appendChild(li);
  }
  if (!opps.length) list.innerHTML = '<li class="dim">— none currently open —</li>';
}

/* ----- health ----- */
function renderHealth(doc) {
  if (!doc) return;
  const sources = doc.data?.sources || {};
  const grid = $('health-grid');
  grid.innerHTML = '';
  let bad = 0;
  for (const [name, s] of Object.entries(sources)) {
    const age = s.last_success ? (Date.now() - new Date(s.last_success).getTime()) / 1000 : Infinity;
    let cls = 'bad';
    if (s.last_success && age < (s.interval_s || 60) * 2) cls = 'ok';
    else if (s.last_success && age < (s.interval_s || 60) * 5) cls = 'warn';
    if (cls === 'bad') bad++;
    grid.innerHTML += `<span class="h-item"><span class="h-dot ${cls}"></span>${name}</span>`;
  }
  $('health-summary').textContent = bad === 0 ? 'SYSTEM OK' : `DEGRADED (${bad})`;
}

/* ----- helpers ----- */
function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function simpleMarkdown(md) {
  // Tiny renderer: ###, **, - lists. Enough for the hot-take output we produce.
  const lines = md.split('\n');
  let out = '';
  let inUl = false;
  for (let line of lines) {
    line = line.trimEnd();
    if (line.startsWith('### ')) {
      if (inUl) { out += '</ul>'; inUl = false; }
      out += `<h3>${escapeHtml(line.slice(4))}</h3>`;
    } else if (line.startsWith('- ')) {
      if (!inUl) { out += '<ul>'; inUl = true; }
      out += `<li>${escapeHtml(line.slice(2)).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')}</li>`;
    } else if (!line) {
      if (inUl) { out += '</ul>'; inUl = false; }
    } else {
      if (inUl) { out += '</ul>'; inUl = false; }
      out += `<p>${escapeHtml(line).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')}</p>`;
    }
  }
  if (inUl) out += '</ul>';
  return out;
}

/* ----- main poll loop ----- */
async function refreshAll() {
  const results = await Promise.all(SOURCES.map(fetchSource));
  const [email, calendar, weather, stocks, hardware, headlines, hottake, grants, health] =
    results;
  renderEmail(email);
  renderCalendar(calendar);
  renderWeather(weather);
  renderStocks(stocks);
  renderHardware(hardware);
  renderNews(headlines, hottake);
  renderGrants(grants);
  renderHealth(health);
}

setInterval(refreshAll, POLL_MS);
refreshAll();

// Boot animation marker — peel off the .boot class after first paint.
requestAnimationFrame(() => {
  setTimeout(() => document.body.classList.remove('boot'), 800);
});

/* ----- controls ----- */
$('refresh-btn').addEventListener('click', () => refreshAll());
$('close-btn').addEventListener('click', () => window.close());
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') window.close();
  if (e.key === 'r' || e.key === 'R') refreshAll();
});

/* Claude pill = pop out to a real terminal with full Claude Code. */
$('claude-btn').addEventListener('click', async () => {
  const link = document.createElement('a');
  link.href = 'claude-cli://launch';
  link.click();
  try {
    await fetch(`${STATE_BASE}/launch/claude`, { method: 'POST' });
  } catch (_) { /* deep link probably worked */ }
});

/* In-panel Claude chat (Anthropic API direct, no MCP/Bash/files). */
const claudeLog = $('claude-log');
const claudeInput = $('claude-input');
const claudeForm = $('claude-form');
const claudeSend = $('claude-send');
const claudeHistory = [];   // [{role:'user'|'assistant', content:'...'}]
const CLAUDE_HISTORY_CAP = 12;

function appendClaudeMsg(role, text) {
  const el = document.createElement('div');
  el.className = `claude-msg claude-msg-${role}`;
  el.textContent = text;
  claudeLog.appendChild(el);
  claudeLog.scrollTop = claudeLog.scrollHeight;
  return el;
}

async function sendClaudeMessage(text) {
  appendClaudeMsg('user', text);
  claudeHistory.push({ role: 'user', content: text });
  while (claudeHistory.length > CLAUDE_HISTORY_CAP) claudeHistory.shift();

  const placeholder = appendClaudeMsg('assistant', '');
  placeholder.classList.add('thinking');
  claudeSend.disabled = true;

  try {
    const r = await fetch(`${STATE_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: claudeHistory }),
    });
    if (!r.ok) {
      const errText = await r.text();
      throw new Error(`HTTP ${r.status}: ${errText.slice(0, 200)}`);
    }
    const j = await r.json();
    const reply = (j.text || '').trim() || '(empty reply)';
    placeholder.classList.remove('thinking');
    placeholder.textContent = reply;
    claudeHistory.push({ role: 'assistant', content: reply });
  } catch (e) {
    placeholder.remove();
    appendClaudeMsg('error', `error: ${e.message}`);
    claudeHistory.pop();   // un-push the user message so retry doesn't double up
  } finally {
    claudeSend.disabled = false;
  }
}

claudeForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = claudeInput.value.trim();
  if (!text) return;
  claudeInput.value = '';
  sendClaudeMessage(text);
});

// Enter to send (Shift+Enter for newline).
claudeInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    claudeForm.requestSubmit();
  }
});
