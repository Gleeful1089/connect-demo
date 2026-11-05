// Single-page UI for the onboarding workbench.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = (x) => (x === null || x === undefined ? 'n/a' : `${Math.round(x * 100)}%`);
const FIELDS = ['category', 'bed', 'view', 'max_occupancy', 'meal_plan', 'cancellation', 'prepaid'];
const CHOICES = {
  category: ['standard', 'superior', 'deluxe', 'suite', 'family'], bed: ['king', 'queen', 'twin', 'two_queens', 'double', 'unspecified'],
  view: ['city', 'ocean', 'garden', 'lake', 'none'], meal_plan: ['room_only', 'breakfast', 'half_board'],
  cancellation: ['free_48h', 'free_24h', 'non_refundable', 'unspecified'], prepaid: ['true', 'false'],
  max_occupancy: ['1', '2', '3', '4', '5', '6', '7', '8'],
};

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}
function toast(m) { const t = $('toast'); t.textContent = m; t.hidden = false; setTimeout(() => { t.hidden = true; }, 6000); }
const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message); } };


function showTab(n) {
  for (const i of [0, 1]) { $('s' + i).hidden = n !== i; $('t' + i).classList.toggle('on', n === i); }
  try { localStorage.setItem('tab', String(n)); } catch (e) { /* storage may be blocked; the tab is a convenience */ }
  window.scrollTo(0, 0);
}
let startTab = 0;   // first visit lands on About; afterwards the last tab used
try { const t = localStorage.getItem('tab'); if (t !== null) startTab = Math.min(1, Math.max(0, +t || 0)); } catch (e) { startTab = 0; }
showTab(startTab);

let TAXO = [];
async function loadAll() {
  const [meta, q] = await Promise.all([api('/api/meta'), api('/api/queue')]);
  TAXO = q.taxonomy;
  $('simflag').innerHTML = meta.simulated
    ? '<span class="sim" title="No ANTHROPIC_API_KEY. Model outputs come from a keyword heuristic, not a language model.">Simulated model outputs (offline fixtures)</span>'
    : `<span class="sim">${esc(meta.llm_mode)} model</span>`;
  if (meta.sandbox) $('sandbox').innerHTML = `<span class="pill" title="Your own copy of the data. Nothing you do here is visible to other users, and it is removed after ${meta.sandbox.ttl_days} days of inactivity.">Personal sandbox ${esc(meta.sandbox.id)}</span>`;
  $('thr').value = q.threshold; $('thrLabel').textContent = (+q.threshold).toFixed(2);
  renderQueue(q); renderTaxo(q.taxonomy);
  await Promise.all([renderRecords(), renderAudit()]);
}

function renderQueue(q) {
  const el = $('queue');
  if (!q.items.length) { el.innerHTML = '<div class="card mute">Queue is empty.</div>'; return; }
  el.innerHTML = q.items.map((it) => {
    const pending = it.new_class_pending;
    const proposed = it.kind === 'mapping'
      ? FIELDS.map((f) => `<span class="pill">${f}: ${esc(it.proposed[f])}</span>`).join(' ')
      : `<span class="pill ${pending ? 'warn' : ''}">class: ${esc(it.proposed.class ?? 'unclassified')}${pending ? ' (new, needs approval)' : ''}</span>`;
    const evidence = it.kind === 'anomaly' ? `<div class="small mute">Rule: ${esc(it.rule)}. Evidence: ${esc(JSON.stringify(it.evidence))}</div>` : '';
    const override = it.kind === 'mapping'
      ? FIELDS.map((f) => `<label class="small">${f} <select data-f="${f}"><option value="">keep</option>${CHOICES[f].map((v) => `<option>${v}</option>`).join('')}</select></label>`).join(' ')
      : `<label class="small">class <select data-f="class"><option value="">no class (record override only)</option>${TAXO.filter((t) => t.status === 'approved').map((t) => `<option>${esc(t.name)}</option>`).join('')}</select></label>`;
    return `<div class="card" data-id="${esc(it.item_id)}">
      <div class="row"><strong>${esc(it.title)}</strong><span class="pill">priority ${it.priority}</span>
        <span class="pill ${it.confidence >= q.threshold ? 'ok' : 'warn'}">model confidence ${(+it.confidence).toFixed(2)}</span>
        <span class="small mute">${esc(it.hotel)} | ${esc(it.model_version)}${it.provenance === 'simulated' ? ' (simulated)' : ''}</span></div>
      <div style="margin:6px 0">${proposed}</div>${evidence}
      ${it.rationale ? `<div class="small mute">Model rationale: ${esc(it.rationale)}</div>` : ''}
      <div class="small"><strong>Proposed fix (class playbook):</strong> ${esc(it.fix)}</div>
      ${it.fix_preview ? `<div class="small"><strong>Automatic fix (deterministic, writes data):</strong> ${esc(it.fix_preview)}. The mapping then returns to the queue for confirmation.</div>` : ''}
      ${it.note ? `<div class="small err">Parse note: ${esc(it.note)}</div>` : ''}
      <div class="row" style="margin-top:8px">${override}
        <input class="note" placeholder="note (optional)" style="flex:1;min-width:140px">
        ${it.fix_preview ? `<button class="act" title="Writes to the data" onclick="applyFix('${esc(it.item_id)}')">Approve and apply fix</button>` : ''}
        <button class="${it.fix_preview ? 'alt' : 'act'}" onclick="decide('${esc(it.item_id)}','approve')">${it.fix_preview ? 'Approve without applying' : 'Approve'}</button>
        <button class="alt" onclick="decide('${esc(it.item_id)}','override')">Override</button></div></div>`;
  }).join('');
}

const decide = guard(async (id, action) => {
  const card = document.querySelector(`[data-id="${CSS.escape(id)}"]`);
  const override = {};
  card.querySelectorAll('select').forEach((s) => { if (s.value) override[s.dataset.f] = s.dataset.f === 'prepaid' ? s.value === 'true' : (s.dataset.f === 'max_occupancy' ? +s.value : s.value); });
  await api(`/api/queue/${encodeURIComponent(id)}/decide`, { action, override: action === 'override' ? override : null, note: card.querySelector('.note').value });
  await loadAll();
});

function renderTaxo(rows) {
  $('taxo').innerHTML = `<table><tr><th>Class</th><th>Description</th><th>Status</th><th></th></tr>${rows.map((t) => `<tr><td>${esc(t.name)}</td><td>${esc(t.description)}</td>
    <td><span class="pill ${t.status === 'approved' ? 'ok' : t.status === 'proposed' ? 'warn' : 'bad'}">${esc(t.status)}</span></td>
    <td>${t.status === 'proposed' ? `<button class="act" onclick="classDecision('${esc(t.name)}',true)">Approve class</button> <button class="alt" onclick="classDecision('${esc(t.name)}',false)">Reject</button>` : ''}</td></tr>`).join('')}</table>
    <div class="small mute" style="margin-top:6px">Vendor and chain are metadata tags on an anomaly. They are never part of a class. The model may propose a class, but only a human can approve it.</div>`;
}
const applyFix = guard(async (id) => {
  const card = document.querySelector(`[data-id="${CSS.escape(id)}"]`);
  await api(`/api/queue/${encodeURIComponent(id)}/fix`, { note: card.querySelector('.note').value });
  await loadAll();
});
const classDecision = guard(async (name, approve) => { await api(`/api/taxonomy/${encodeURIComponent(name)}`, { approve }); await loadAll(); });

async function renderRecords() {
  const rows = await api('/api/records');
  const counts = rows.reduce((a, r) => { a[r.status] = (a[r.status] || 0) + 1; return a; }, {});
  $('counts').textContent = Object.entries(counts).map(([k, v]) => `${v} ${k.replace('_', '-')}`).join(', ');
  $('records').innerHTML = `<tr><th>ID</th><th>Hotel</th><th>Fmt</th><th>Room (raw)</th><th>Plan (raw)</th><th class="n">Rate</th>${FIELDS.map((f) => `<th>${f.replace('_', ' ')}</th>`).join('')}<th>Mapping</th><th class="n">Conf</th><th>Open anomalies</th></tr>` +
    rows.map((r) => `<tr><td>${r.id}</td><td>${esc(r.hotel)}</td><td>${r.format}</td><td>${esc(r.room)}</td><td>${esc(r.plan)}</td><td class="n">${(r.rate_cents / 100).toFixed(2)} ${esc(r.currency)}</td>
      ${FIELDS.map((f) => { const m = r.final || r.proposed; return `<td title="${r.final ? 'human-confirmed' : 'model proposal'}">${esc(String(m[f] ?? '—'))}</td>`; }).join('')}
      <td><span class="pill ${r.status === 'review' ? 'warn' : 'ok'}">${r.status.replace('_', '-')}</span></td><td class="n">${(+r.confidence).toFixed(2)}</td>
      <td>${r.anomalies.map((a) => `<span class="pill bad">${esc(a)}</span>`).join(' ')}</td></tr>`).join('');
}


async function renderAudit() {
  const rows = await api('/api/audit');
  $('audit').innerHTML = rows.length ? `<tr><th>Time (UTC)</th><th>Item</th><th>Model version</th><th class="n">Model conf</th><th>Human action</th><th>Final</th><th>Actor</th></tr>` +
    rows.map((r) => `<tr><td>${esc(r.ts)}</td><td>${esc(r.item_id)}</td><td>${esc(r.model_version)}</td><td class="n">${r.model_confidence == null ? 'n/a' : (+r.model_confidence).toFixed(2)}</td><td>${esc(r.human_action)}</td><td class="small">${esc(r.final)}</td><td>${esc(r.actor)}</td></tr>`).join('')
    : '<tr><td class="mute">No decisions yet. Approve or override an item in the queue.</td></tr>';
}

const setThr = guard(async (v) => { await api('/api/threshold', { threshold: +v }); await loadAll(); });
const rebuild = guard(async () => { await api('/api/pipeline/run', {}); await loadAll(); });

loadAll().catch((e) => { document.body.insertAdjacentHTML('afterbegin', `<div class="card err">Failed to load: ${esc(e.message)}</div>`); });
