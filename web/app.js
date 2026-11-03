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


let TAXO = [];
async function loadAll() {
  const [meta, q] = await Promise.all([api('/api/meta'), api('/api/queue')]);
  TAXO = q.taxonomy;
  $('simflag').innerHTML = meta.simulated
    ? '<span class="sim" title="No ANTHROPIC_API_KEY. Model outputs come from a keyword heuristic, not a language model.">Simulated model outputs (offline fixtures)</span>'
    : `<span class="sim">${esc(meta.llm_mode)} model</span>`;
  $('thr').value = q.threshold; $('thrLabel').textContent = (+q.threshold).toFixed(2);
  renderQueue(q); renderTaxo(q.taxonomy);
  await Promise.all([renderRecords(), renderEval(q.threshold), renderAudit()]);
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
        <span class="pill ${it.confidence >= 0.85 ? 'ok' : 'warn'}">model confidence ${(+it.confidence).toFixed(2)}</span>
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
  $('records').innerHTML = `<tr><th>ID</th><th>Hotel</th><th>Fmt</th><th>Room (raw)</th><th>Plan (raw)</th><th class="n">Rate</th><th>Mapping</th><th class="n">Conf</th><th>Open anomalies</th></tr>` +
    rows.map((r) => `<tr><td>${r.id}</td><td>${esc(r.hotel)}</td><td>${r.format}</td><td>${esc(r.room)}</td><td>${esc(r.plan)}</td><td class="n">${(r.rate_cents / 100).toFixed(2)} ${esc(r.currency)}</td>
      <td><span class="pill ${r.status === 'review' ? 'warn' : 'ok'}">${r.status.replace('_', '-')}</span></td><td class="n">${(+r.confidence).toFixed(2)}</td>
      <td>${r.anomalies.map((a) => `<span class="pill bad">${esc(a)}</span>`).join(' ')}</td></tr>`).join('');
}

let EVAL_T = null;
async function renderEval(t) {
  EVAL_T = t;
  const ev = await api(`/api/eval?threshold=${t}`);
  const cur = ev.current;
  const simNote = ev.provenance.includes('simulated')
    ? '<div class="small" style="color:var(--sim)">These numbers score a keyword-heuristic stand-in, not a language model. They show the mechanics of the panel. Record real outputs with an API key to measure a model.</div>' : '';
  $('eval').innerHTML = `${simNote}
    <div class="row"><strong>Threshold</strong><input type="range" min="0.5" max="1" step="0.05" value="${t}" style="width:220px" oninput="evalLabel.textContent=(+this.value).toFixed(2)" onchange="renderEval(+this.value)"><span id="evalLabel" class="pill">${(+t).toFixed(2)}</span></div>
    <div class="row" style="margin:8px 0"><span class="pill ok">precision ${pct(cur.precision)} (${Math.round((cur.precision ?? 0) * cur.n_auto)}/${cur.n_auto} auto-confirmed)</span>
      <span class="pill">recall ${pct(cur.recall)}</span><span class="pill">coverage ${pct(cur.coverage)} (${cur.n_auto}/${cur.n_total})</span></div>
    <div class="small mute">Computed only on the ${ev.n_heldout} held-out records. Correct = all 7 canonical fields match the label. Precision = correct among auto-confirmed. Recall = correct and auto-confirmed over all correct proposals. With n=${ev.n_heldout}, one record moves a number by 12 points or more.</div>
    ${curveSvg(ev.curve, t)}
    <table><tr><th>Threshold</th><th class="n">Auto-confirmed</th><th class="n">Precision</th><th class="n">Recall</th><th class="n">Coverage</th></tr>${ev.curve.map((c) => `<tr class="${Math.abs(c.threshold - t) < 0.001 ? 'hl' : ''}"><td>${c.threshold.toFixed(2)}</td><td class="n">${c.n_auto}/${c.n_total}</td><td class="n">${pct(c.precision)}</td><td class="n">${pct(c.recall)}</td><td class="n">${pct(c.coverage)}</td></tr>`).join('')}</table>
    <h2 style="margin-top:12px">Held-out records</h2>
    <table><tr><th>ID</th><th class="n">Confidence</th><th>Result</th><th>Wrong fields</th></tr>${ev.records.map((r) => `<tr><td>${r.record_id}</td><td class="n">${r.confidence.toFixed(2)}</td><td><span class="pill ${r.correct ? 'ok' : 'bad'}">${r.correct ? 'correct' : 'wrong'}</span></td><td>${r.wrong_fields.map((f) => `${esc(f)}: proposed ${esc(r.proposed[f])}, label ${esc(r.truth[f])}`).join('; ')}</td></tr>`).join('')}</table>
    <div class="small" style="margin-top:8px">Anomaly classification on held-out anomalies: ${ev.classification.correct}/${ev.classification.expected} correct (${pct(ev.classification.accuracy)}).</div>`;
}
function curveSvg(curve, t) {
  const W = 360, H = 120, x = (v) => 30 + ((v - 0.5) / 0.5) * (W - 40), y = (v) => H - 20 - v * (H - 40);
  const line = (key, color) => curve.filter((c) => c[key] !== null).map((c, i) => `${i ? 'L' : 'M'}${x(c.threshold).toFixed(1)},${y(c[key]).toFixed(1)}`).join(' ');
  return `<svg viewBox="0 0 ${W} ${H}" style="max-width:420px;width:100%" role="img" aria-label="Precision and recall by threshold">
    <path d="${line('precision')}" fill="none" stroke="var(--ok)" stroke-width="2"/><path d="${line('recall')}" fill="none" stroke="var(--acc)" stroke-width="2"/>
    <line x1="${x(t)}" x2="${x(t)}" y1="10" y2="${H - 20}" stroke="var(--mute)" stroke-dasharray="3"/>
    <text x="30" y="${H - 4}" font-size="10" fill="var(--mute)">0.5</text><text x="${W - 22}" y="${H - 4}" font-size="10" fill="var(--mute)">1.0</text>
    <text x="36" y="12" font-size="10" fill="var(--ok)">precision</text><text x="90" y="12" font-size="10" fill="var(--acc)">recall</text></svg>`;
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
