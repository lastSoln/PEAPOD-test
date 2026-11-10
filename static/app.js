/* Peapod plan test bench: one page, plain JS. All planning happens on the server in engine/. */
(() => {
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = v => '$' + (Math.round(v * 100) / 100).toString();
const CAPS = ['#FFC83D', '#3B95E6', '#9467E3', '#FF7F4F', '#1BA38E', '#79C850', '#E8553F', '#B2DE93', '#DBC4FF', '#9CDAFF'];
const PARTS = [['majority', 'Majority'], ['match_sum', 'Match sum'], ['no_chip', 'No chip'], ['fairness', 'Fairness'],
  ['variety', 'Variety'], ['distance', 'Distance'], ['price', 'Price'], ['new_slot', 'New slot'], ['jitter', 'Jitter']];
const LS = 'peapod.bench.v1';

const S = {
  meta: null, pod: { name: '', members: [] }, openPicker: -1,
  req: { kind: 'dayout', date: '', start: '11:00', area: '', budget: '', hub: '' },
  weights: {}, seed: 1, tierCuts: [40, 100], label: '',
  result: null, fb: { plan_score: null, plan_note: '', stops: {} },
  cmp: { a: null, b: null, seedA: 1, seedB: 1, out: null },
  runs: null, busy: false,
};

/* ---------- helpers ---------- */
function toast(msg, err) {
  const t = $('#toast'); t.textContent = msg; t.className = 'toast' + (err ? ' err' : ''); t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, err ? 5000 : 2200);
}
async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (res.status === 401) { location.href = '/login'; throw new Error('Signed out'); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || ('Request failed (' + res.status + ')'));
  return data;
}
function tiers() {
  const [a, b] = S.tierCuts;
  return [{ key: 'low', label: 'Under $' + a, min: 0, max: a }, { key: 'mid', label: '$' + a + ' to $' + b, min: a, max: b },
    { key: 'high', label: '$' + b + ' and over', min: b, max: null }];
}
function config(weights, seed) { return { weights: weights || S.weights, seed: seed ?? S.seed, budget_tiers: tiers() }; }
function niceDate(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-SG', { weekday: 'short', day: 'numeric', month: 'short' });
}
function save() {
  try { localStorage.setItem(LS, JSON.stringify({ pod: S.pod, req: S.req, weights: S.weights, seed: S.seed, tierCuts: S.tierCuts, tester: $('#tester').value, cmp: { a: S.cmp.a, b: S.cmp.b, seedA: S.cmp.seedA, seedB: S.cmp.seedB } })); } catch (e) { /* storage is optional */ }
}
function load() { try { return JSON.parse(localStorage.getItem(LS) || 'null'); } catch (e) { return null; } }
function defaultWeights() { return Object.fromEntries(S.meta.weights.map(w => [w.key, w.default])); }
function newMember(i) {
  return { name: 'Member ' + (i + 1), chips: [], budget_tier: 'mid', over18: true, home: { zone: 'Central' }, needs: '' };
}
function showTab(side, tab) {
  $$(`[data-tabs="${side}"] button`).forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
  const ids = side === 'left' ? ['pod', 'request', 'weights'] : ['result', 'debug', 'compare', 'runs'];
  ids.forEach(id => { $('#tab-' + id).hidden = id !== tab; });
  if (tab === 'runs') loadRuns();
  if (tab === 'result') setTimeout(drawMap, 0);
}
const chipHtml = (c, cls = '') => `<span class="chip ${cls}">${esc(c)}</span>`;

/* ---------- Pod builder ---------- */
function podProblems() {
  const n = S.pod.members.length, out = [];
  if (n < 3 || n > 10) out.push('A pod needs 3 to 10 members (now ' + n + ').');
  S.pod.members.forEach(m => { if (m.chips.length < 3 || m.chips.length > 5) out.push((m.name || 'A member') + ' needs 3 to 5 chips.'); });
  return out;
}
function renderPod() {
  const M = S.meta, T = tiers();
  const members = S.pod.members.map((m, i) => {
    const coords = m.home && m.home.lat !== undefined;
    const bad = m.chips.length < 3 || m.chips.length > 5;
    const picker = S.openPicker !== i ? '' : `<div class="picker">${M.tiles.map(t => t.chips.length ? `
      <div class="label">${esc(t.label)}</div><div class="chips">${t.chips.map(c => `
        <button class="chip ${m.chips.includes(c.name) ? 'on' : ''}" data-act="chip" data-i="${i}" data-chip="${esc(c.name)}" title="${esc(c.hub)}">${esc(c.name)} <small>${c.count}</small></button>`).join('')}</div>` : '').join('')}</div>`;
    return `<div class="member ${bad ? 'bad' : ''}">
      <div class="row"><span class="cap" style="background:${CAPS[i % CAPS.length]}">${esc((m.name || '?')[0].toUpperCase())}</span>
        <input class="grow" data-f="name" data-i="${i}" value="${esc(m.name)}" aria-label="Member name">
        <button class="icon-btn" data-act="rm-member" data-i="${i}" title="Remove member" aria-label="Remove ${esc(m.name)}">×</button></div>
      <div class="chips">${m.chips.map(c => `<button class="chip on" data-act="chip" data-i="${i}" data-chip="${esc(c)}" title="Remove">${esc(c)} ×</button>`).join('')}
        <button class="chip dim" data-act="picker" data-i="${i}">${S.openPicker === i ? 'Done' : 'Pick interests'} · ${m.chips.length}/5</button></div>
      ${picker}
      <div class="row"><div class="seg" role="radiogroup" aria-label="Budget tier">${T.map(t => `<button class="${m.budget_tier === t.key ? 'on' : ''}" data-act="tier" data-i="${i}" data-v="${t.key}">${esc(t.label)}</button>`).join('')}</div>
        <label class="row" style="gap:6px"><input type="checkbox" data-f="over18" data-i="${i}" ${m.over18 ? 'checked' : ''}> Over 18</label></div>
      <div class="row"><span class="label">Home</span>
        <select data-f="homezone" data-i="${i}">${M.zones.map(z => `<option ${!coords && m.home.zone === z ? 'selected' : ''}>${esc(z)}</option>`).join('')}<option value="__c" ${coords ? 'selected' : ''}>Coordinates…</option></select>
        ${coords ? `<input style="width:96px" data-f="lat" data-i="${i}" value="${esc(m.home.lat)}" placeholder="lat" aria-label="Latitude"><input style="width:96px" data-f="lng" data-i="${i}" value="${esc(m.home.lng)}" placeholder="lng" aria-label="Longitude">` : ''}</div>
      <input data-f="needs" data-i="${i}" value="${esc(m.needs || '')}" placeholder="Needs (stored, not used by the engine)" aria-label="Needs">
    </div>`;
  }).join('');
  const probs = podProblems();
  $('#tab-pod').innerHTML = `<div class="stack">
    <div class="section-head"><h2 class="grow">Pod · ${S.pod.members.length} ${S.pod.members.length === 1 ? 'pea' : 'peas'}</h2>
      <button class="btn small" data-act="random-pod">Random pod</button></div>
    <div class="row"><select class="grow" id="example" aria-label="Example pods"><option value="">Load an example pod…</option>${M.examples.map((e, i) => `<option value="${i}">${esc(e.name)}</option>`).join('')}</select></div>
    ${probs.length ? `<div class="note coral">${probs.map(esc).join('<br>')}</div>` : ''}
    ${members}
    <button class="btn ghost" data-act="add-member" ${S.pod.members.length >= 10 ? 'disabled' : ''}>+ Add a member</button>
  </div>`;
  renderSummary(); save();
}

/* ---------- Plan request ---------- */
function renderRequest() {
  const M = S.meta, r = S.req, T = tiers();
  const opt = (v, label, cur) => `<option value="${esc(v)}" ${cur === v ? 'selected' : ''}>${esc(label)}</option>`;
  $('#tab-request').innerHTML = `<div class="stack">
    <h2>New plan</h2>
    <div class="seg big" role="radiogroup" aria-label="Kind of plan">
      <button class="${r.kind === 'moment' ? 'on' : ''}" data-act="kind" data-v="moment">Moment</button>
      <button class="${r.kind === 'dayout' ? 'on' : ''}" data-act="kind" data-v="dayout">Day out</button></div>
    <div class="muted">${r.kind === 'moment' ? 'One stop, such as a dinner or a coffee.' : '3 to 5 stops that flow together across the day.'}</div>
    <div class="row end"><label class="field"><span class="label">Date</span><input type="date" data-r="date" value="${esc(r.date)}"></label>
      <label class="field"><span class="label">Start (Singapore time)</span><input type="time" data-r="start" value="${esc(r.start)}" step="300"></label></div>
    <div class="label">Fixed rows (optional)</div>
    <label class="field"><span class="label">Area</span><select data-r="area">${opt('', 'Anywhere', r.area)}${M.zones.map(z => opt(z, z, r.area)).join('')}</select></label>
    <label class="field"><span class="label">Budget</span><select data-r="budget">${opt('', "The pod's lowest budget", r.budget)}${T.map(t => opt(t.key, t.label, r.budget)).join('')}</select></label>
    <label class="field"><span class="label">Kind</span><select data-r="hub">${opt('', 'Any kind', r.hub)}${M.hubs.map(h => opt(h, h, r.hub)).join('')}</select></label>
    <label class="field"><span class="label">Run label (optional, saved with the run)</span><input data-r="label" value="${esc(S.label)}" placeholder="e.g. foodies, default weights"></label>
    <div class="note">Hours are typical estimates (about 89% are not confirmed) and prices are estimates. A fixed Budget row can only lower the limit, never raise it above the pod's lowest budget.</div>
  </div>`;
  renderSummary();
}
function renderSummary() {
  const r = S.req, fixed = [r.area, r.budget && tiers().find(t => t.key === r.budget).label, r.hub].filter(Boolean);
  $('#req-summary').textContent = `${r.kind === 'moment' ? 'Moment' : 'Day out'} · ${niceDate(r.date)} · ${r.start} · ${fixed.length ? fixed.join(' · ') : 'nothing fixed'} · seed ${S.seed}`;
}

/* ---------- Weights ---------- */
function renderWeights() {
  const rows = S.meta.weights.map(w => `<div class="weight ${S.weights[w.key] !== w.default ? 'changed' : ''}">
    <span class="name">${esc(w.label)}</span>
    <input type="number" data-w="${w.key}" value="${S.weights[w.key]}" min="${w.min}" max="${w.max}" step="${w.step}" aria-label="${esc(w.label)}">
    <input type="range" data-w="${w.key}" value="${S.weights[w.key]}" min="${w.min}" max="${w.max}" step="${w.step}" style="grid-column:1/-1" aria-label="${esc(w.label)} slider">
    <span class="help">${esc(w.help)} Default ${w.default}.</span></div>`).join('');
  $('#tab-weights').innerHTML = `<div class="stack">
    <div class="section-head"><h2 class="grow">Weights</h2><button class="btn small" data-act="reset-weights">Reset to defaults</button></div>
    <div class="row end"><label class="field"><span class="label">Random seed</span><input type="number" data-seed value="${S.seed}" step="1"></label>
      <button class="btn small" data-act="new-seed">New seed</button></div>
    <div class="muted">The same pod, request, weights and seed always give the same plan.</div>
    <div>${rows}</div>
    <div class="label">Budget tiers (whole day, SGD per person)</div>
    <div class="row end"><label class="field"><span class="label">Low is under</span><input type="number" data-cut="0" value="${S.tierCuts[0]}" min="1" step="5"></label>
      <label class="field"><span class="label">High starts at</span><input type="number" data-cut="1" value="${S.tierCuts[1]}" min="2" step="5"></label></div>
    <div class="btn-row"><button class="btn primary grow" data-act="plan">Run again with these weights</button></div>
    <div class="btn-row"><button class="btn small" data-act="to-a">Copy to compare set A</button><button class="btn small" data-act="to-b">Copy to compare set B</button></div>
  </div>`;
}

/* ---------- Result ---------- */
function checksHtml(ch) {
  return `<div class="checks">${ch.items.map(c => `<div class="check ${c.pass ? '' : 'fail'}"><b>${c.pass ? '✓' : '✕'}</b><span>${esc(c.label)}<small>${esc(c.detail)}</small></span></div>`).join('')}</div>`;
}
function matchChips(matched) {
  const by = {};
  matched.forEach(m => m.chips.forEach(c => { (by[c] = by[c] || { level: m.level, names: [] }).names.push(m.name); if (m.level === 'exact') by[c].level = 'exact'; }));
  const hubOnly = matched.filter(m => m.level === 'hub').map(m => m.name);
  return Object.entries(by).map(([c, v]) => `<span class="chip ${v.level}" title="${v.level === 'exact' ? 'Exact chip' : 'Same tile'}">${esc(c)} · ${esc(v.names.join(', '))}</span>`).join('')
    + (hubOnly.length ? `<span class="chip hub" title="Matched by hub only">Kind only · ${esc(hubOnly.join(', '))}</span>` : '');
}
function stopHtml(s, withFeedback) {
  const p = s.place, f = S.fb.stops[s.index] || {};
  const leg = s.leg ? `<div class="leg">${s.leg.minutes} min ${s.leg.mode === 'walk' ? 'walk' : 'public transport'} · ${s.leg.km} km</div>` : '';
  const alts = s.alternatives.map(a => `<div class="alt"><b>${esc(a.place.name)}</b><span class="muted">${esc(a.place.hub)} · ~${money(a.place.price_est)} · ${a.km} km · score ${a.score.toFixed(2)}</span><span class="grow"></span><span class="muted">${esc(a.why)}</span></div>`).join('');
  const links = [p.website && `<a class="link" href="${esc(p.website)}" target="_blank" rel="noopener noreferrer">Website</a>`, p.phone && `<span class="muted">${esc(p.phone)}</span>`,
    `<a class="link" href="https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lng}" target="_blank" rel="noopener noreferrer">Map</a>`].filter(Boolean).join(' · ');
  const fbRow = !withFeedback ? '' : `<div class="fb"><div class="seg">${['good', 'ok', 'bad'].map(v => `<button class="${f.verdict === v ? 'on ' + v : ''}" data-act="verdict" data-i="${s.index}" data-v="${v}">${v === 'ok' ? 'OK' : v[0].toUpperCase() + v.slice(1)}</button>`).join('')}</div>
      <select data-fb="reason" data-i="${s.index}" aria-label="Reason"><option value="">Reason…</option>${S.meta.reasons.map(r => `<option ${f.reason === r ? 'selected' : ''}>${esc(r)}</option>`).join('')}</select>
      <input class="grow" data-fb="note" data-i="${s.index}" value="${esc(f.note || '')}" placeholder="Note" aria-label="Note"></div>`;
  return `${leg}<div class="card stop"><div class="n ${s.is_new_slot ? 'new' : ''}">${s.index + 1}</div><div>
    <div class="stop-head"><span class="time">${s.arrival}–${s.depart}</span><h3>${esc(p.name)}</h3>${s.is_new_slot ? '<span class="chip new">Something new</span>' : ''}</div>
    <div class="facts">${esc(p.hub)} · ${esc(p.zone)} · ${s.duration} min · ~${money(s.price_est)} per person (est. ${money(p.price_min)}–${money(p.price_max)})${p.indoor_outdoor ? ' · ' + esc(p.indoor_outdoor) : ''} · typical hours ${esc((p.hours_today || []).join(', ') || 'unknown')}</div>
    <div class="chips">${matchChips(s.matched) || '<span class="chip dim">No taste match</span>'}</div>
    <div class="why">${esc(s.why)}</div>
    <div class="muted" style="font-size:12.5px">${p.address ? esc(p.address) + ' · ' : ''}${links} · score ${s.score.toFixed(2)}</div>
    ${alts ? `<details><summary>${s.alternatives.length} alternatives</summary>${alts}</details>` : ''}
    ${fbRow}</div></div>`;
}
function renderResult() {
  const R = S.result, el = $('#tab-result');
  if (!R) { el.innerHTML = `<div class="empty-state"><h2>No plan yet</h2><p>Build a pod on the left, set the request, then press <b>Plan it</b>.</p></div>`; return; }
  const title = `${R.kind === 'moment' ? 'Moment' : 'Day out'} · ${niceDate(R.date)} · ${R.start}`;
  if (R.status !== 'ok') {
    el.innerHTML = `<div class="hero"><div class="grow"><h2>${esc(title)}</h2><div class="meta">Run #${R.run_id} · seed ${R.seed}</div></div><span class="pill fail">No plan</span></div>
      <div class="card" style="margin-top:16px"><h3>${esc(R.message)}</h3><p class="muted">Nothing was relaxed to force a plan. The Debug tab shows how many places survived each filter.</p>
      <div class="row"><span class="label">Rate this outcome</span><div class="score">${[1, 2, 3, 4, 5].map(n => `<button class="${S.fb.plan_score === n ? 'on' : ''}" data-act="score" data-v="${n}">${n}</button>`).join('')}</div>
      <input class="grow" data-fb="plan_note" value="${esc(S.fb.plan_note)}" placeholder="Was failing the right call?"></div></div>`;
    return;
  }
  const ch = R.checks, allOk = ch.passed === ch.total;
  const leave = R.leave_home.map(m => `<tr><td><b>${esc(m.name)}</b>${m.km !== null ? `<br><span class="muted">${m.km} km</span>` : ''}</td>${m.modes
    ? ['walk', 'transit', 'car', 'cab'].map(k => `<td class="num ${k === 'walk' && m.modes[k].minutes > 60 ? 'muted' : ''}">${m.modes[k].leave}<br><span class="muted">${m.modes[k].minutes} min</span></td>`).join('')
    : '<td colspan="4" class="muted">No saved home</td>'}</tr>`).join('');
  el.innerHTML = `<div class="hero"><div class="grow"><h2>${esc(title)}</h2>
      <div class="meta">${R.stops.length} ${R.stops.length === 1 ? 'stop' : 'stops'} · ends about ${R.end} · ~${money(R.total_cost)} per person · budget ${esc(R.budget_label)} · run #${R.run_id} · seed ${R.seed}</div></div>
      <span class="pill ${allOk ? '' : 'fail'}">Checks ${ch.passed}/${ch.total}</span>
      <a class="btn" style="display:inline-grid;place-items:center;text-decoration:none" href="${esc(R.map_url)}" target="_blank" rel="noopener noreferrer">Open route in Maps</a></div>
    <div class="result-grid"><div>
      ${R.stops.map(s => stopHtml(s, true)).join('')}
      <div class="card"><div class="row"><h3 class="grow">Score this plan</h3><span class="muted" id="fb-status"></span></div>
        <div class="row" style="margin-top:8px"><div class="score" role="radiogroup" aria-label="Plan score 1 to 5">${[1, 2, 3, 4, 5].map(n => `<button class="${S.fb.plan_score === n ? 'on' : ''}" data-act="score" data-v="${n}">${n}</button>`).join('')}</div>
        <input class="grow" data-fb="plan_note" value="${esc(S.fb.plan_note)}" placeholder="Anything about the plan as a whole" aria-label="Plan note"></div>
        <div class="muted" style="margin-top:6px;font-size:12px">Feedback saves as you go, together with the pod, request, weights and output.</div></div>
    </div><div>
      <div class="card"><h3>Sanity checks</h3>${checksHtml(ch)}</div>
      <div class="card"><h3>Leave home at</h3><div class="muted" style="font-size:12px">To reach stop 1 by ${R.start}. Straight line × detour ÷ speed.</div>
        <div class="scroll-x"><table><thead><tr><th>Member</th><th class="num">Walk</th><th class="num">Public</th><th class="num">Car</th><th class="num">Cab</th></tr></thead><tbody>${leave}</tbody></table></div></div>
      <div class="card"><h3>Map</h3><div id="map"></div><div class="muted" style="font-size:12px;margin-top:6px">Green pins are stops in order; blue dots are homes.</div></div>
      <div class="note" style="margin-top:12px">${esc(R.hours_note)}</div>
    </div></div>`;
  drawMap();
}
let map = null;
function drawMap() {
  const el = $('#map'), R = S.result;
  if (map) { map.remove(); map = null; }
  if (!el || !R || R.status !== 'ok' || !window.L || $('#tab-result').hidden) { if (el && !window.L) el.outerHTML = '<div class="muted">Map library did not load. Use "Open route in Maps".</div>'; return; }
  map = L.map(el, { scrollWheelZoom: false });
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap contributors' }).addTo(map);
  const pts = R.stops.map(s => [s.place.lat, s.place.lng]);
  R.stops.forEach((s, i) => L.marker(pts[i], { icon: L.divIcon({ className: '', html: `<div class="map-pin">${i + 1}</div>`, iconSize: [26, 26], iconAnchor: [13, 13] }) }).addTo(map).bindTooltip(`${i + 1}. ${s.place.name} · ${s.arrival}`));
  if (pts.length > 1) L.polyline(pts, { color: '#1E3A26', weight: 3, dashArray: '6 6' }).addTo(map);
  const all = pts.slice();
  S.pod.members.forEach(m => {
    const h = m.home || {}, c = h.lat !== undefined ? [Number(h.lat), Number(h.lng)] : S.meta.zone_centroids[h.zone];
    if (!c || !isFinite(c[0]) || !isFinite(c[1])) return;
    L.marker(c, { icon: L.divIcon({ className: '', html: '<div class="map-home"></div>', iconSize: [12, 12], iconAnchor: [6, 6] }) }).addTo(map).bindTooltip(m.name + ' (home)');
    all.push(c);
  });
  map.fitBounds(L.latLngBounds(pts.length > 1 ? pts : all).pad(0.25), { maxZoom: 15 });
}

/* ---------- Debug ---------- */
function funnelHtml(rows) {
  const max = Math.max(1, ...rows.map(r => r.count));
  return rows.map(r => `<div class="bar-row"><span>${esc(r.label)}</span><span class="bar"><i style="width:${(100 * r.count / max).toFixed(1)}%"></i></span><span class="mono" style="text-align:right">${r.count.toLocaleString()}</span></div>`).join('');
}
function partCell(v) { return `<td class="num ${v < 0 ? 'neg' : v > 0 ? 'pos' : 'muted'}">${v === 0 ? '·' : v.toFixed(2)}</td>`; }
function topTable(rows) {
  return `<div class="scroll-x"><table><thead><tr><th>#</th><th>Place</th><th>Chips</th><th class="num">Score</th>${PARTS.map(p => `<th class="num">${p[1]}</th>`).join('')}<th class="num">Share</th><th class="num">km</th><th>Matched members</th></tr></thead><tbody>
    ${rows.map(r => `<tr class="${r.chosen ? 'chosen' : ''}"><td class="num">${r.rank}</td><td><b>${esc(r.place.name)}</b><br><span class="muted">${esc(r.place.hub)} · ${esc(r.place.zone)} · ~${money(r.place.price_est)} · ${r.arrival}</span></td>
      <td>${r.place.chips.map(esc).join(', ') || '<span class="muted">none</span>'}</td><td class="num"><b>${r.score.toFixed(2)}</b></td>${PARTS.map(p => partCell(r.parts[p[0]])).join('')}
      <td class="num">${Math.round(r.share * 100)}%</td><td class="num">${r.km}</td><td>${r.matched.map(m => `${esc(m.name)} <span class="muted">(${m.level})</span>`).join(', ') || '<span class="muted">nobody</span>'}</td></tr>`).join('')}</tbody></table></div>`;
}
function renderDebug() {
  const R = S.result, el = $('#tab-debug');
  if (!R) { el.innerHTML = '<div class="empty-state"><h2>Nothing to debug yet</h2><p>Run a plan first.</p></div>'; return; }
  const D = R.debug, hubMax = Math.max(1, ...Object.values(D.hub_counts));
  const cov = D.coverage.length ? `<div class="card"><h3>Which members each stop matched</h3><div class="scroll-x"><table><thead><tr><th>Member</th>${R.stops.map(s => `<th>${s.index + 1}. ${esc(s.place.name.slice(0, 22))}</th>`).join('')}<th>Served</th></tr></thead><tbody>
    ${D.coverage.map(c => `<tr><td><b>${esc(c.name)}</b></td>${c.stops.map(l => `<td>${l ? `<span class="chip ${l}">${l === 'hub' ? 'kind only' : l}</span>` : '<span class="muted">·</span>'}</td>`).join('')}<td>${c.stops.some(l => l === 'exact' || l === 'tile') ? '✓' : '<span style="color:var(--coral-text)">no match</span>'}</td></tr>`).join('')}</tbody></table></div></div>` : '';
  const stops = D.per_stop.map(ps => {
    const st = R.stops[ps.index];
    const basis = st ? `<details><summary>Where the chosen place's data came from (basis)</summary><div class="chips" style="margin-top:6px">${Object.entries(st.place.basis || {}).map(([k, v]) => `<span class="chip ${v === 'estimated' ? 'tile' : v === 'unknown' || v === 'none' ? 'dim' : 'exact'}">${esc(k)}: ${esc(v)}</span>`).join('')}</div></details>` : '';
    return `<div class="card"><div class="section-head"><h3 class="grow">Stop ${ps.index + 1}${st ? ' · ' + esc(st.place.name) : ' · no candidate'}</h3>
      ${ps.is_new_slot ? '<span class="chip new">Something-new slot</span>' : ''}${ps.loosened_hub_mix ? '<span class="chip tile">Hub mix loosened</span>' : ''}</div>
      <div class="muted" style="margin-bottom:8px">${esc(ps.slot)}: ${ps.allowed_hubs.map(esc).join(', ') || 'none'}</div>
      ${funnelHtml(ps.funnel)}
      ${ps.top.length ? `<div class="label" style="margin:12px 0 4px">Top ${ps.top.length} candidates, score broken into parts</div>${topTable(ps.top)}` : ''}${basis}</div>`;
  }).join('');
  el.innerHTML = `<div class="section-head"><h2 class="grow">Debug · run #${R.run_id}</h2><span class="pill ${R.status === 'ok' ? '' : 'fail'}">${R.status === 'ok' ? 'Checks ' + R.checks.passed + '/' + R.checks.total : 'No plan'}</span></div>
    ${R.status !== 'ok' ? `<div class="note coral" style="margin-bottom:12px">${esc(R.message)}</div>` : ''}${(D.notes || []).map(n => `<div class="note" style="margin-bottom:12px">${esc(n)}</div>`).join('')}
    <div class="kv"><div><span class="label">Lowest budget</span><b>${esc(R.budget_label)}</b></div><div><span class="label">Price target per stop</span><b>${money(D.price_target_per_stop)}</b></div>
      <div><span class="label">Everyone over 18</span><b>${D.all_over_18 ? 'Yes' : 'No'}</b></div><div><span class="label">Hubs the pod wants</span><b style="font-size:13px">${D.wanted_hubs.map(esc).join(', ') || 'none'}</b></div></div>
    <div class="two" style="margin-top:12px"><div class="card"><h3>Filter: places that survived each hard limit</h3><div style="margin-top:8px">${funnelHtml(D.funnel)}</div></div>
      <div class="card" style="margin-top:0"><h3>Eligible places per hub</h3><div class="muted" style="font-size:12px">A hub with fewer than 3 is "empty".</div><div style="margin-top:8px">
      ${Object.entries(D.hub_counts).map(([h, n]) => `<div class="bar-row ${D.empty_hubs.includes(h) ? 'empty' : ''}"><span>${esc(h)}${D.empty_hubs.includes(h) ? ' <span class="chip" style="height:18px;color:var(--coral-text)">empty</span>' : ''}</span><span class="bar"><i style="width:${(100 * n / hubMax).toFixed(1)}%"></i></span><span class="mono" style="text-align:right">${n.toLocaleString()}</span></div>`).join('')}</div></div></div>
    ${cov}${stops}
    <details class="card"><summary>Weights used for this run</summary><pre class="mono" style="white-space:pre-wrap;font-size:12px">${esc(JSON.stringify(R.config, null, 2))}</pre></details>`;
}

/* ---------- Compare ---------- */
function renderCompare() {
  const C = S.cmp, el = $('#tab-compare');
  if (!C.a) C.a = { ...S.weights }; if (!C.b) C.b = { ...S.weights };
  const rows = S.meta.weights.map(w => `<tr><td>${esc(w.label)}<br><span class="muted">default ${w.default}</span></td>
    ${['a', 'b'].map(k => `<td class="${C.a[w.key] !== C.b[w.key] ? 'diff' : ''}"><input type="number" style="width:90px" data-cw="${k}" data-k="${w.key}" value="${C[k][w.key]}" min="${w.min}" max="${w.max}" step="${w.step}" aria-label="${esc(w.label)} set ${k.toUpperCase()}"></td>`).join('')}</tr>`).join('');
  let out = '';
  if (C.out) {
    const col = (R, name) => R.status !== 'ok'
      ? `<div class="card" style="margin-top:0"><h3>Set ${name} · run #${R.run_id}</h3><div class="note coral" style="margin-top:8px">${esc(R.message)}</div></div>`
      : `<div class="card" style="margin-top:0"><div class="section-head"><h3 class="grow">Set ${name} · run #${R.run_id}</h3><span class="pill ${R.checks.passed === R.checks.total ? '' : 'fail'}">Checks ${R.checks.passed}/${R.checks.total}</span>
          <button class="btn small" data-act="open-cmp" data-v="${name.toLowerCase()}">Open in Result</button></div>
        <div class="muted">~${money(R.total_cost)} per person · ends ${R.end} · seed ${R.seed}</div>
        ${R.checks.items.filter(c => !c.pass).map(c => `<div class="note coral" style="margin-top:6px">${esc(c.label)}: ${esc(c.detail)}</div>`).join('')}</div>`;
    const A = C.out.a, B = C.out.b, n = Math.max(A.stops.length, B.stops.length);
    const cell = (s, other) => !s ? '<td class="muted">—</td>' : `<td class="${other && other.place.id === s.place.id ? '' : 'diff'}"><span class="mono">${s.arrival}</span> <b>${esc(s.place.name)}</b><br><span class="muted">${esc(s.place.hub)} · ~${money(s.price_est)} · score ${s.score.toFixed(2)}${s.leg ? ' · ' + s.leg.minutes + ' min leg' : ''}</span><br>${matchChips(s.matched)}<br><span class="muted">${esc(s.why)}</span></td>`;
    const same = A.stops.filter((s, i) => B.stops[i] && B.stops[i].place.id === s.place.id).length;
    out = `<div class="two" style="margin-top:16px">${col(A, 'A')}${col(B, 'B')}</div>
      <div class="card"><div class="section-head"><h3 class="grow">Stops side by side</h3><span class="pill sun">${same} of ${n} stops the same</span></div>
      <div class="scroll-x"><table><thead><tr><th>#</th><th style="width:48%">Set A</th><th style="width:48%">Set B</th></tr></thead><tbody>
      ${Array.from({ length: n }, (_, i) => `<tr><td class="num">${i + 1}</td>${cell(A.stops[i], B.stops[i])}${cell(B.stops[i], A.stops[i])}</tr>`).join('')}</tbody></table></div>
      <div class="muted" style="font-size:12px;margin-top:6px">Highlighted cells differ between the two sets.</div></div>`;
  }
  el.innerHTML = `<div class="section-head"><h2 class="grow">Compare two weight sets</h2><button class="btn primary" data-act="run-compare">Run both on this pod and request</button></div>
    <div class="muted" style="margin-bottom:10px">Same pod, same request, two sets of weights. Both runs are saved and linked.</div>
    <div class="card"><div class="scroll-x"><table><thead><tr><th>Weight</th><th>Set A <button class="btn small" data-act="to-a">Use current</button></th><th>Set B <button class="btn small" data-act="to-b">Use current</button></th></tr></thead><tbody>${rows}
      <tr><td>Random seed</td><td><input type="number" style="width:90px" data-cseed="A" value="${C.seedA}"></td><td><input type="number" style="width:90px" data-cseed="B" value="${C.seedB}"></td></tr></tbody></table></div></div>${out}`;
}

/* ---------- Runs ---------- */
async function loadRuns() {
  try { S.runs = await api('/api/runs'); renderRuns(); } catch (e) { toast(e.message, true); }
}
function renderRuns() {
  const el = $('#tab-runs'), D = S.runs;
  if (!D) { el.innerHTML = '<div class="empty-state">Loading runs…</div>'; return; }
  const st = D.stats, pct = st.checks_total ? Math.round(100 * st.checks_passed / st.checks_total) : null;
  const v = st.verdicts || {};
  el.innerHTML = `<div class="section-head"><h2 class="grow">Saved runs</h2>
      <a class="btn small" style="display:inline-grid;place-items:center;text-decoration:none" href="/api/export.csv?level=stops">Export CSV (one row per stop)</a>
      <a class="btn small" style="display:inline-grid;place-items:center;text-decoration:none" href="/api/export.csv?level=runs">Export CSV (one row per run)</a></div>
    <div class="kv"><div><span class="label">Runs</span><b>${st.runs}</b>${st.planned} produced a plan</div>
      <div><span class="label">Sanity checks passed</span><b>${pct === null ? '–' : pct + '%'}</b>${st.checks_passed} of ${st.checks_total} · ${st.clean_runs} clean runs</div>
      <div><span class="label">Average plan score</span><b>${st.avg_plan_score ?? '–'}</b>${st.scored_runs} scored</div>
      <div><span class="label">Stop verdicts</span><b style="font-size:14px">${v.good || 0} good · ${v.ok || 0} OK · ${v.bad || 0} bad</b>${Object.entries(st.reasons || {}).map(([k, n]) => esc(k) + ' ' + n).join(' · ')}</div></div>
    <div class="card"><div class="scroll-x"><table><thead><tr><th>#</th><th>When (SGT)</th><th>Tester</th><th>Label</th><th>Request</th><th class="num">Checks</th><th class="num">Cost</th><th class="num">Score</th><th></th></tr></thead><tbody>
    ${D.runs.map(r => `<tr><td class="num">${r.id}</td><td class="mono">${esc(r.created_at.slice(0, 16).replace('T', ' '))}</td><td>${esc(r.tester || '')}</td><td>${esc(r.label || '')}</td>
      <td>${r.kind === 'moment' ? 'Moment' : 'Day out'} · ${esc(niceDate(r.request.date))} ${esc(r.request.start || '')}${[r.request.area, r.request.hub].filter(Boolean).map(x => ' · ' + esc(x)).join('')}</td>
      <td class="num ${r.status !== 'ok' || r.checks_passed < r.checks_total ? 'neg' : 'pos'}">${r.status === 'ok' ? r.checks_passed + '/' + r.checks_total : 'no plan'}</td><td class="num">${r.status === 'ok' ? money(r.total_cost) : ''}</td>
      <td class="num">${r.plan_score ?? (r.has_feedback ? '•' : '')}</td><td><button class="btn small" data-act="open-run" data-v="${r.id}">Open</button></td></tr>`).join('') || '<tr><td colspan="9" class="muted">No runs yet.</td></tr>'}</tbody></table></div></div>`;
}

/* ---------- actions ---------- */
function setResult(R, fb) {
  S.result = R;
  S.fb = { plan_score: fb?.plan_score ?? null, plan_note: fb?.plan_note || '', stops: Object.fromEntries((fb?.stops || []).map(s => [s.index, s])) };
  renderResult(); renderDebug();
}
async function runPlan() {
  const probs = podProblems();
  if (probs.length) { showTab('left', 'pod'); renderPod(); return toast(probs[0], true); }
  if (S.busy) return; S.busy = true;
  $$('[data-act="plan"],[data-act="surprise"]').forEach(b => { b.disabled = true; });
  try {
    const R = await api('/api/plan', { pod: S.pod, request: S.req, config: config(), tester: $('#tester').value, label: S.label });
    setResult(R); showTab('right', 'result');
    toast(R.status === 'ok' ? `Planned · checks ${R.checks.passed}/${R.checks.total}` : 'No plan fits', R.status !== 'ok');
  } catch (e) { toast(e.message, true); }
  S.busy = false; $$('[data-act="plan"],[data-act="surprise"]').forEach(b => { b.disabled = false; });
}
let fbTimer = null;
function saveFeedback() {
  if (!S.result) return;
  clearTimeout(fbTimer);
  fbTimer = setTimeout(async () => {
    const st = $('#fb-status');
    try {
      await api(`/api/runs/${S.result.run_id}/feedback`, { plan_score: S.fb.plan_score, plan_note: S.fb.plan_note, stops: Object.entries(S.fb.stops).map(([i, s]) => ({ index: Number(i), ...s })) });
      if (st) st.textContent = 'Feedback saved';
    } catch (e) { toast(e.message, true); }
  }, 400);
}

document.addEventListener('click', async e => {
  const tab = e.target.closest('.tabs button');
  if (tab) return showTab(tab.parentElement.dataset.tabs, tab.dataset.tab);
  const b = e.target.closest('[data-act]'); if (!b) return;
  const act = b.dataset.act, i = Number(b.dataset.i), v = b.dataset.v, m = S.pod.members[i];
  switch (act) {
    case 'add-member': S.pod.members.push(newMember(S.pod.members.length)); S.openPicker = S.pod.members.length - 1; renderPod(); break;
    case 'rm-member': S.pod.members.splice(i, 1); S.openPicker = -1; renderPod(); break;
    case 'picker': S.openPicker = S.openPicker === i ? -1 : i; renderPod(); break;
    case 'chip': {
      const c = b.dataset.chip, at = m.chips.indexOf(c);
      if (at >= 0) m.chips.splice(at, 1); else if (m.chips.length >= 5) return toast('Up to 5 chips per member', true); else m.chips.push(c);
      renderPod(); break;
    }
    case 'tier': m.budget_tier = v; renderPod(); break;
    case 'random-pod': try { S.pod = await api('/api/random-pod'); S.openPicker = -1; renderPod(); } catch (err) { toast(err.message, true); } break;
    case 'kind': S.req.kind = v; renderRequest(); save(); break;
    case 'surprise': Object.assign(S.req, { kind: 'dayout', area: '', budget: '', hub: '' }); renderRequest(); save(); runPlan(); break;
    case 'plan': runPlan(); break;
    case 'reset-weights': S.weights = defaultWeights(); renderWeights(); save(); break;
    case 'new-seed': S.seed = Math.floor(Math.random() * 100000); renderWeights(); renderSummary(); save(); break;
    case 'to-a': S.cmp.a = { ...S.weights }; S.cmp.seedA = S.seed; renderCompare(); save(); toast('Current weights copied to set A'); break;
    case 'to-b': S.cmp.b = { ...S.weights }; S.cmp.seedB = S.seed; renderCompare(); save(); toast('Current weights copied to set B'); break;
    case 'run-compare': {
      const probs = podProblems(); if (probs.length) return toast(probs[0], true);
      b.disabled = true;
      try {
        S.cmp.out = await api('/api/compare', { pod: S.pod, request: S.req, config_a: config(S.cmp.a, S.cmp.seedA), config_b: config(S.cmp.b, S.cmp.seedB), tester: $('#tester').value, label: S.label });
      } catch (err) { toast(err.message, true); }
      renderCompare(); break;
    }
    case 'open-cmp': setResult(S.cmp.out[v]); showTab('right', 'result'); break;
    case 'open-run': try {
      const run = await api('/api/runs/' + v);
      S.pod = run.pod; S.req = Object.assign({ area: '', budget: '', hub: '' }, run.request);
      S.weights = Object.assign(defaultWeights(), run.config.weights); S.seed = run.config.seed;
      const t = run.config.budget_tiers; if (t && t[0].max && t[1].max) S.tierCuts = [t[0].max, t[1].max];
      S.label = run.label || '';
      const R = run.result; R.run_id = run.id; R.config = run.config;
      renderPod(); renderRequest(); renderWeights();
      setResult(R, { plan_score: run.plan_score, plan_note: run.plan_note, stops: run.feedback });
      showTab('right', 'result'); toast('Run #' + run.id + ' loaded with its pod, request and weights');
    } catch (err) { toast(err.message, true); } break;
    case 'verdict': { const f = S.fb.stops[i] = S.fb.stops[i] || {}; f.verdict = f.verdict === v ? '' : v; renderResult(); saveFeedback(); break; }
    case 'score': S.fb.plan_score = S.fb.plan_score === Number(v) ? null : Number(v); renderResult(); saveFeedback(); break;
  }
});

document.addEventListener('input', e => {
  const t = e.target, d = t.dataset;
  if (d.f) {
    const m = S.pod.members[Number(d.i)];
    if (d.f === 'name') m.name = t.value;
    else if (d.f === 'needs') m.needs = t.value;
    else if (d.f === 'lat' || d.f === 'lng') m.home[d.f] = t.value;
    save(); return;
  }
  if (d.r) { if (d.r === 'label') S.label = t.value; else S.req[d.r] = t.value; renderSummary(); save(); return; }
  if (d.w) {
    const spec = S.meta.weights.find(w => w.key === d.w), n = Number(t.value);
    if (t.value === '' || !isFinite(n)) return;
    S.weights[d.w] = Math.min(spec.max, Math.max(spec.min, n));
    $$(`[data-w="${d.w}"]`).forEach(o => { if (o !== t) o.value = S.weights[d.w]; });
    t.closest('.weight').classList.toggle('changed', S.weights[d.w] !== spec.default); save(); return;
  }
  if (d.seed !== undefined) { S.seed = Math.round(Number(t.value)) || 0; renderSummary(); save(); return; }
  if (d.cw) { const n = Number(t.value); if (t.value !== '' && isFinite(n)) { S.cmp[d.cw][d.k] = n; save(); } return; }
  if (d.cseed) { S.cmp['seed' + d.cseed] = Math.round(Number(t.value)) || 0; save(); return; }
  if (d.fb === 'note') { (S.fb.stops[Number(d.i)] = S.fb.stops[Number(d.i)] || {}).note = t.value; saveFeedback(); return; }
  if (d.fb === 'plan_note') { S.fb.plan_note = t.value; saveFeedback(); return; }
  if (t.id === 'tester') save();
});

document.addEventListener('change', e => {
  const t = e.target, d = t.dataset;
  if (t.id === 'example' && t.value !== '') { S.pod = JSON.parse(JSON.stringify(S.meta.examples[Number(t.value)])); S.openPicker = -1; renderPod(); return; }
  if (d.f === 'over18') { S.pod.members[Number(d.i)].over18 = t.checked; save(); return; }
  if (d.f === 'homezone') {
    const m = S.pod.members[Number(d.i)];
    if (t.value === '__c') { const c = S.meta.zone_centroids[m.home.zone] || [1.3521, 103.8198]; m.home = { lat: c[0], lng: c[1] }; } else m.home = { zone: t.value };
    renderPod(); return;
  }
  if (d.f === 'name') { renderPod(); return; }
  if (d.fb === 'reason') { (S.fb.stops[Number(d.i)] = S.fb.stops[Number(d.i)] || {}).reason = t.value; saveFeedback(); return; }
  if (d.cut !== undefined) {
    const n = Math.max(1, Math.round(Number(t.value)) || 0); S.tierCuts[Number(d.cut)] = n;
    if (S.tierCuts[1] <= S.tierCuts[0]) S.tierCuts[1] = S.tierCuts[0] + 10;
    renderWeights(); renderPod(); renderRequest(); save(); return;
  }
  if (d.cw) renderCompare();
});

/* ---------- start ---------- */
(async () => {
  try { S.meta = await api('/api/meta'); } catch (e) { return toast(e.message, true); }
  const M = S.meta, saved = load();
  S.weights = defaultWeights(); S.seed = M.seed; S.tierCuts = [M.budget_tiers[0].max, M.budget_tiers[1].max];
  S.req.date = M.defaults.date; S.req.start = M.defaults.start;
  S.pod = JSON.parse(JSON.stringify(M.examples[0]));
  if (saved) {
    if (saved.pod?.members?.length) S.pod = saved.pod;
    if (saved.req) Object.assign(S.req, saved.req);
    if (!S.req.date || S.req.date < M.defaults.today) S.req.date = M.defaults.date;
    if (saved.weights) M.weights.forEach(w => { if (typeof saved.weights[w.key] === 'number') S.weights[w.key] = saved.weights[w.key]; });
    if (typeof saved.seed === 'number') S.seed = saved.seed;
    if (Array.isArray(saved.tierCuts)) S.tierCuts = saved.tierCuts;
    if (saved.cmp) Object.assign(S.cmp, saved.cmp);
    $('#tester').value = saved.tester || '';
  }
  $('#dataset-note').textContent = `${M.dataset.places.toLocaleString()} active places · ${M.dataset.chips} chips · ${M.dataset.no_chip.toLocaleString()} with no chip (matched by kind only) · Singapore time`;
  renderPod(); renderRequest(); renderWeights(); renderResult(); renderDebug(); renderCompare(); renderRuns();
})();
})();
