/* Peapod plan test bench: one page, plain JS. All planning happens on the server in engine/. */
(() => {
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = v => '$' + (Math.round(v * 100) / 100).toString();
const CAPS = ['#FFC83D', '#3B95E6', '#9467E3', '#FF7F4F', '#1BA38E', '#79C850', '#E8553F', '#B2DE93', '#DBC4FF', '#9CDAFF'];
const PARTS = [['majority', 'Majority'], ['match_sum', 'Match'], ['no_chip', 'No chip'], ['fairness', 'Fair'], ['variety', 'Variety'],
  ['distance', 'Dist'], ['price', 'Price'], ['new_slot', 'New'], ['style', 'Style'], ['jitter', 'Jitter']];
const LS = 'peapod.bench.v2';

const S = {
  meta: null, pod: { name: '', members: [] }, openMember: -1,
  req: { kind: 'dayout', date: '', start: '11:00', area: '', budget: '', hub: '' },
  pitcher: '', weights: {}, seed: 1, tierCuts: [40, 100], label: '', tester: '',
  session: null, newPlan: true, votes: {}, actor: '',
  fb: { plan_score: null, plan_note: '', stops: {} }, fbRun: null,
  cmp: { a: null, b: null, seedA: 1, seedB: 1, out: null },
  logTab: 'events', runs: null, rules: null, busy: false,
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
  const [a, b] = S.tierCuts, L = S.meta.budget_tiers;
  return [{ key: 'low', label: L[0].label, sub: 'under $' + a, min: 0, max: a }, { key: 'mid', label: L[1].label, sub: '$' + a + ' to $' + b, min: a, max: b },
    { key: 'high', label: L[2].label, sub: '$' + b + ' and up', min: b, max: null }];
}
function config(weights, seed) { return { weights: weights || S.weights, seed: seed ?? S.seed, budget_tiers: tiers() }; }
function niceDate(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-SG', { weekday: 'short', day: 'numeric', month: 'short' });
}
function save() {
  try {
    localStorage.setItem(LS, JSON.stringify({ pod: S.pod, req: S.req, pitcher: S.pitcher, weights: S.weights, seed: S.seed, tierCuts: S.tierCuts,
      tester: S.tester, label: S.label, sessionId: S.session?.id || null, cmp: { a: S.cmp.a, b: S.cmp.b, seedA: S.cmp.seedA, seedB: S.cmp.seedB } }));
  } catch (e) { /* storage is optional */ }
}
function load() { try { return JSON.parse(localStorage.getItem(LS) || 'null'); } catch (e) { return null; } }
function defaultWeights() { return Object.fromEntries(S.meta.weights.map(w => [w.key, w.default])); }
function newMember(i) {
  return { name: 'Member ' + (i + 1), interests: [], favourites: [], budget_tier: 'mid', travel: 'town', style: 'flow', over18: true, home: { zone: 'Central' }, needs: '' };
}
const tile = k => S.meta.tiles.find(t => t.key === k);
const label = (list, k) => (list.find(x => x.key === k) || {}).label || k;
const reasonLabel = k => label([...S.meta.practical_reasons, ...S.meta.not_for_me_reasons], k);
const capOf = name => { const i = S.pod.members.findIndex(m => m.name === name); return CAPS[(i < 0 ? 0 : i) % CAPS.length]; };
const capHtml = (name, sm) => `<span class="cap ${sm ? 'sm' : ''}" style="background:${capOf(name)}">${esc((name || '?')[0].toUpperCase())}</span>`;
function seg(opts, cur, attrs, cls = '') {
  return `<div class="seg ${cls}">${opts.map(o => `<button type="button" class="${cur === o.key ? 'on ' + (o.cls || '') : ''}" ${attrs} data-v="${esc(o.key)}">${esc(o.label)}</button>`).join('')}</div>`;
}
function setView(v) {
  document.body.dataset.view = v;
  $$('.tabs button').forEach(b => b.classList.toggle('on', b.dataset.view === v || (v === 'pod' && b.dataset.view === 'plan' && innerWidth >= 1040)));
  if (v === 'log') renderLog();
  if (v === 'inspect') setTimeout(drawMap, 30);
  scrollTo({ top: 0 });
}
function sheet(html) { $('#sheet-body').innerHTML = html; $('#sheet').hidden = false; }
function closeSheet() { $('#sheet').hidden = true; }

/* ---------- Pod ---------- */
function memberProblem(m) {
  const n = (m.interests || []).length;
  return n < 3 || n > 5 ? 'pick 3 to 5 interests' : '';
}
function podProblems() {
  const n = S.pod.members.length, out = [];
  if (n < 3 || n > 10) out.push('A pod needs 3 to 10 members (now ' + n + ').');
  const names = S.pod.members.map(m => (m.name || '').trim());
  if (new Set(names).size !== names.length || names.some(x => !x)) out.push('Every member needs a different name.');
  S.pod.members.forEach(m => { const p = memberProblem(m); if (p) out.push(`${m.name || 'A member'}: ${p}.`); });
  return out;
}
function memberSummary(m) {
  const T = tiers();
  return [(m.interests || []).map(k => (tile(k) || {}).label).filter(Boolean).join(', ') || 'no interests yet',
    label(T, m.budget_tier), label(S.meta.travel_prefs, m.travel), label(S.meta.styles, m.style)].join(' · ');
}
function renderPod() {
  const M = S.meta, T = tiers();
  const members = S.pod.members.map((m, i) => {
    const coords = m.home && m.home.lat !== undefined, bad = memberProblem(m);
    const taste = m.taste || {}, learned = Object.keys(taste.down || {}).length + Object.keys(taste.up || {}).length + (taste.rest || []).length;
    const favs = (m.interests || []).map(k => tile(k)).filter(t => t && t.chips.length).map(t => `
      <div><div class="label">${esc(t.label)}</div><div class="chips" style="margin-top:4px">${t.chips.map(c => `
        <button type="button" class="chip tiny ${m.favourites.includes(c.name) ? 'on' : ''}" data-act="fav" data-i="${i}" data-chip="${esc(c.name)}">${m.favourites.includes(c.name) ? '♥ ' : ''}${esc(c.name)} <small>${c.count}</small></button>`).join('')}</div></div>`).join('');
    return `<details class="member ${bad ? 'bad' : ''}" data-i="${i}" ${S.openMember === i ? 'open' : ''}>
      <summary>${capHtml(m.name)}<span class="who"><b>${esc(m.name || 'Unnamed')}</b><span>${bad ? '<span style="color:var(--coral-text)">' + esc(bad) + '</span>' : esc(memberSummary(m))}</span></span></summary>
      <div class="edit">
        <div class="row"><input class="grow" data-f="name" data-i="${i}" value="${esc(m.name)}" aria-label="Name"><button class="btn small danger" data-act="rm-member" data-i="${i}">Remove</button></div>
        <div><div class="label">Interests · pick 3 to 5 (${(m.interests || []).length})</div>
          <div class="tile-grid" style="margin-top:6px">${M.tiles.map(t => `<button type="button" class="tile-btn ${m.interests.includes(t.key) ? 'on' : ''}" data-act="tile" data-i="${i}" data-v="${t.key}">${esc(t.label)}</button>`).join('')}</div></div>
        ${favs ? `<div class="favs"><div class="label">Favourites · optional, tap what they like most</div>${favs}</div>` : ''}
        <div><div class="label">Spend per person (whole day)</div>${seg(T.map(t => ({ key: t.key, label: `${t.label} · ${t.sub}` })), m.budget_tier, `data-act="mset" data-f="budget_tier" data-i="${i}"`)}</div>
        <div><div class="label">How far they usually go (hard limit from home)</div>${seg(M.travel_prefs, m.travel, `data-act="mset" data-f="travel" data-i="${i}"`)}</div>
        <div><div class="label">Plan style (soft)</div>${seg(M.styles, m.style, `data-act="mset" data-f="style" data-i="${i}"`)}
          <div class="muted small" style="margin-top:4px">${esc((M.styles.find(s => s.key === m.style) || {}).does || '')}</div></div>
        <div class="row end"><label class="field"><span class="label">Home (their saved place)</span>
          <select data-f="homezone" data-i="${i}">${M.zones.map(z => `<option ${!coords && m.home.zone === z ? 'selected' : ''}>${esc(z)}</option>`).join('')}<option value="__c" ${coords ? 'selected' : ''}>Exact coordinates…</option></select></label>
          <label class="row" style="min-height:42px"><input type="checkbox" data-f="over18" data-i="${i}" ${m.over18 ? 'checked' : ''}> Over 18</label></div>
        ${coords ? `<div class="row"><input class="grow" data-f="lat" data-i="${i}" value="${esc(m.home.lat)}" placeholder="latitude" inputmode="decimal" aria-label="Latitude"><input class="grow" data-f="lng" data-i="${i}" value="${esc(m.home.lng)}" placeholder="longitude" inputmode="decimal" aria-label="Longitude"></div>` : ''}
        <input data-f="needs" data-i="${i}" value="${esc(m.needs || '')}" placeholder="Needs (stored, not used by the engine)" aria-label="Needs">
        ${learned ? `<div class="note"><b>Learned taste</b> from votes and hearts:
          ${Object.entries(taste.down || {}).map(([c, x]) => `<span class="chip tiny coral">${esc(c)} ×${x}</span>`).join(' ')}
          ${Object.entries(taste.up || {}).map(([c, x]) => `<span class="chip tiny exact">${esc(c)} ×${x}</span>`).join(' ')}
          ${(taste.rest || []).length ? `<span class="chip tiny">${taste.rest.length} places resting</span>` : ''}
          <button class="btn small" data-act="reset-taste" data-i="${i}" style="margin-top:6px">Forget it</button></div>` : ''}
      </div></details>`;
  }).join('');
  const probs = podProblems();
  $('#v-pod').innerHTML = `<div class="stack">
    <div class="head"><h2 class="grow">Your pod · ${S.pod.members.length} ${S.pod.members.length === 1 ? 'pea' : 'peas'}</h2><button class="btn small" data-act="random-pod">Random</button></div>
    <select id="example" aria-label="Example pods"><option value="">Load an example pod…</option>${M.examples.map((e, i) => `<option value="${i}">${esc(e.name)}</option>`).join('')}</select>
    ${probs.length ? `<div class="note coral">${probs.map(esc).join('<br>')}</div>` : ''}
    ${members}
    <button class="btn wide" data-act="add-member" ${S.pod.members.length >= 10 ? 'disabled' : ''}>+ Add a pea</button>
    <button class="btn primary wide only-mobile" data-act="go-plan">Next: plan something</button>
  </div>`;
  save();
}

/* ---------- Plan: the form ---------- */
function planForm() {
  const M = S.meta, r = S.req, T = tiers();
  const opt = (v, text, cur) => `<option value="${esc(v)}" ${cur === v ? 'selected' : ''}>${esc(text)}</option>`;
  const fixed = [r.area, r.budget, r.hub].filter(Boolean).length;
  return `<div class="stack">
    <div class="head"><h2 class="grow">New plan</h2>${S.session ? '<button class="btn small" data-act="back-plan">Back to the plan</button>' : ''}</div>
    ${seg([{ key: 'moment', label: 'Moment' }, { key: 'dayout', label: 'Day out' }], r.kind, 'data-act="kind"')}
    <div class="muted small">${r.kind === 'moment' ? 'One stop, such as a dinner or a coffee.' : '3 to 5 stops that flow together across the day.'}</div>
    <div class="row end"><label class="field"><span class="label">Date</span><input type="date" data-r="date" value="${esc(r.date)}"></label>
      <label class="field"><span class="label">Start · Singapore time</span><input type="time" data-r="start" value="${esc(r.start)}" step="300"></label></div>
    <label class="field"><span class="label">Who pitches it?</span><select data-r="pitcher">${opt('', 'Peapod pick (everyone swipes)', S.pitcher)}${S.pod.members.map(m => opt(m.name, m.name + ' (they are in, the rest swipe)', S.pitcher)).join('')}</select></label>
    <details class="group" ${fixed ? 'open' : ''}><summary>I have something in mind ${fixed ? `<span class="pill sun">${fixed} fixed</span>` : ''}</summary><div class="body stack">
      <label class="field"><span class="label">Area</span><select data-r="area">${opt('', 'Anywhere', r.area)}${M.zones.map(z => opt(z, z, r.area)).join('')}</select></label>
      <label class="field"><span class="label">Budget</span><select data-r="budget">${opt('', "The pod's lowest budget", r.budget)}${T.map(t => opt(t.key, `${t.label} · ${t.sub}`, r.budget)).join('')}</select></label>
      <label class="field"><span class="label">Kind</span><select data-r="hub">${opt('', 'Any kind', r.hub)}${M.hubs.map(h => opt(h, h, r.hub)).join('')}</select></label></div></details>
    <div class="row end"><label class="field"><span class="label">Tester</span><input data-r="tester" value="${esc(S.tester)}" placeholder="your name"></label>
      <label class="field"><span class="label">Run label</span><input data-r="label" value="${esc(S.label)}" placeholder="optional"></label></div>
    <div class="row"><button class="btn grow" data-act="surprise">Surprise us</button><button class="btn primary grow" data-act="plan">Plan it</button></div>
    <div class="muted small">Seed ${S.seed}. Hours and prices are typical estimates, not confirmed.</div>
  </div>`;
}

/* ---------- Plan: the plan page ---------- */
function matchChips(matched) {
  const by = {};
  matched.forEach(m => m.chips.forEach(c => { (by[c] = by[c] || { level: m.level, names: [] }).names.push(m.name); if (m.level === 'exact') by[c].level = 'exact'; }));
  const hubOnly = matched.filter(m => m.level === 'hub').map(m => m.name);
  return Object.entries(by).map(([c, v]) => `<span class="chip tiny ${v.level}">${esc(c)} · ${esc(v.names.join(', '))}</span>`).join('')
    + (hubOnly.length ? `<span class="chip tiny hub">Kind only · ${esc(hubOnly.join(', '))}</span>` : '');
}
function stopCard(s, P) {
  const p = s.place, f = S.fb.stops[s.index] || {}, phase = P.phase;
  const leg = s.leg ? `<div class="leg">${s.leg.minutes} min ${s.leg.mode === 'walk' ? 'walk' : 'public transport'} · ${s.leg.km} km</div>` : '';
  const hearts = Object.entries(P.hearts || {}).filter(([, ids]) => ids.includes(p.id)).map(([n]) => n);
  const mine = hearts.includes(S.actor);
  const alts = s.alternatives.map(a => `<div class="alt"><b>${esc(a.place.name)}</b> <span class="muted">${esc(a.place.hub)} · ~${money(a.place.price_est)} · score ${a.score.toFixed(2)}</span><br><span class="muted">${esc(a.why)}</span></div>`).join('');
  const links = [p.website && `<a class="link" href="${esc(p.website)}" target="_blank" rel="noopener noreferrer">Website</a>`, p.phone && esc(p.phone),
    `<a class="link" href="https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lng}" target="_blank" rel="noopener noreferrer">Map</a>`].filter(Boolean).join(' · ');
  const tools = phase !== 'planning' ? '' : `<div class="tools">
    <button class="icon-btn ${mine ? 'on' : ''}" data-act="heart" data-i="${s.index}" title="Heart as ${esc(S.actor)}" aria-label="Heart">♥</button>
    <button class="btn small" data-act="change" data-i="${s.index}">Change</button>
    <button class="btn small" data-act="move" data-i="${s.index}" data-v="up" ${s.index === 0 ? 'disabled' : ''} aria-label="Move earlier">↑</button>
    <button class="btn small" data-act="move" data-i="${s.index}" data-v="down" ${s.index === P.plan.stops.length - 1 ? 'disabled' : ''} aria-label="Move later">↓</button>
    <button class="btn small danger" data-act="remove" data-i="${s.index}">Remove</button></div>`;
  return `${leg}<div class="card stop"><div class="n ${s.is_new_slot ? 'new' : ''}">${s.index + 1}</div><div>
    <div class="time">${s.arrival}–${s.depart}${s.is_new_slot ? ' · <span class="chip tiny sun">Something new</span>' : ''}${hearts.length ? ` · <span class="chip tiny coral">♥ ${esc(hearts.join(', '))}</span>` : ''}</div>
    <h3>${esc(p.name)}</h3>
    <div class="facts">${esc(p.hub)} · ${s.duration} min · ~${money(s.price_est)} each</div>
    <div class="why">${esc(s.why)}</div>
    <div class="chips">${matchChips(s.matched)}</div>
    ${tools}
    <details class="more"><summary>Details, alternatives and rating</summary>
      <div class="muted small" style="margin:6px 0">${esc(p.zone)}${p.address ? ' · ' + esc(p.address) : ''} · est. ${money(p.price_min)}–${money(p.price_max)} · typical hours ${esc((p.hours_today || []).join(', ') || 'closed')}${p.hours_confirmed ? ' (confirmed)' : ' (estimate)'}${p.indoor_outdoor ? ' · ' + esc(p.indoor_outdoor) : ''} · ${links} · score ${s.score.toFixed(2)}</div>
      ${alts ? `<div class="label" style="margin-top:8px">Alternatives</div>${alts}` : ''}
      <div class="label" style="margin-top:10px">Rate this stop (tester)</div>
      <div class="row" style="margin-top:4px">${seg([{ key: 'good', label: 'Good', cls: 'in' }, { key: 'ok', label: 'OK', cls: 'maybe' }, { key: 'bad', label: 'Bad', cls: 'cant' }], f.verdict, `data-act="verdict" data-i="${s.index}"`)}</div>
      <div class="row" style="margin-top:6px"><select data-fb="reason" data-i="${s.index}" aria-label="Reason"><option value="">Reason…</option>${S.meta.reasons.map(r => `<option ${f.reason === r ? 'selected' : ''}>${esc(r)}</option>`).join('')}</select>
        <input class="grow" data-fb="note" data-i="${s.index}" value="${esc(f.note || '')}" placeholder="Note" aria-label="Note"></div>
    </details></div></div>`;
}
function votePanel(P) {
  const M = S.meta, final = P.round >= M.max_rounds;
  const asked = Object.entries(P.members).filter(([, s]) => s.status === 'asked').map(([n]) => n);
  const answers = [{ key: 'in', label: "I'm in", cls: 'in' }, ...(final ? [] : [{ key: 'maybe', label: 'Maybe', cls: 'maybe' }]), { key: 'cant', label: "Can't", cls: 'cant' }, { key: '', label: 'No answer' }];
  const rows = asked.map(n => {
    const v = S.votes[n] || { answer: '' }, st = P.members[n];
    let reasons = '';
    if (v.answer === 'maybe') reasons = `<div><div class="label">What would they change?</div><div class="chips" style="margin-top:4px">${M.practical_reasons.map(r => `<button class="chip ${v.reason === r.key ? 'on' : ''}" data-act="reason" data-n="${esc(n)}" data-v="${r.key}">${esc(r.label)}</button>`).join('')}</div></div>`;
    if (v.answer === 'cant') reasons = `<div>${final ? '' : `<div class="label">Want to go · Peapod reworks it</div><div class="chips" style="margin:4px 0 8px">${M.practical_reasons.map(r => `<button class="chip ${v.reason === r.key ? 'on' : ''}" data-act="reason" data-n="${esc(n)}" data-v="${r.key}">${esc(r.label)}</button>`).join('')}</div>`}
      <div class="label">Not for me · they are out</div><div class="chips" style="margin-top:4px">${M.not_for_me_reasons.map(r => `<button class="chip ${v.reason === r.key ? 'on' : ''}" data-act="reason" data-n="${esc(n)}" data-v="${r.key}">${esc(r.label)}</button>`).join('')}</div></div>`;
    return `<div class="voter"><div class="row">${capHtml(n, true)}<b class="grow">${esc(n)}</b>${st.missed ? `<span class="pill fail">${Math.max(0, 3 - st.missed)} ${3 - st.missed === 1 ? 'chance' : 'chances'} left</span>` : ''}</div>
      ${seg(answers, v.answer || '', `data-act="answer" data-n="${esc(n)}"`)}${reasons}</div>`;
  }).join('');
  return `<div class="card"><div class="head"><h3 class="grow">${final ? 'Final round' : 'Round ' + P.round + ' of ' + M.max_rounds} · swipe as each pea</h3><button class="btn small" data-act="all-in">All in</button></div>
    <div class="muted small" style="margin:4px 0 6px">${final ? "I'm in or Can't only. Anyone not in by the end is out." : 'Maybe means they would go with a change. No answer counts as Can\'t with no reason.'}</div>
    ${rows}<button class="btn primary wide" data-act="close-round" style="margin-top:10px">Close the round</button></div>`;
}
function planningPanel(P) {
  const going = Object.entries(P.members).filter(([, s]) => s.status === 'in');
  const out = Object.entries(P.members).filter(([, s]) => s.status === 'out');
  const ready = going.filter(([, s]) => s.approved).length;
  return `<div class="card"><div class="head"><h3 class="grow">It's a plan · ${ready} of ${going.length} approved</h3></div>
    <div class="muted small" style="margin:4px 0 8px">Anyone going can change anything. When everyone going approves, it is locked.</div>
    <label class="field"><span class="label">Edit and heart as</span><select data-actor>${going.map(([n]) => `<option ${S.actor === n ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></label>
    ${going.map(([n, s]) => `<div class="voter"><div class="row">${capHtml(n, true)}<b class="grow">${esc(n)}</b>
      ${s.approved ? `<span class="pill">Approved ✓</span><button class="btn small" data-act="unapprove" data-n="${esc(n)}">Undo</button>` : `<button class="btn small primary" data-act="approve" data-n="${esc(n)}">Approve</button>`}
      <button class="btn small danger" data-act="leave" data-n="${esc(n)}">Leave</button></div></div>`).join('')}
    ${out.map(([n, s]) => `<div class="voter"><div class="row">${capHtml(n, true)}<b class="grow muted">${esc(n)} · not going (${esc(s.out_how || 'out')})</b><button class="btn small" data-act="rejoin" data-n="${esc(n)}">Rejoin</button></div></div>`).join('')}
    <div class="row" style="margin-top:10px"><button class="btn grow" data-act="add-stop">+ Add a stop</button><button class="btn grow" data-act="approve-all">Everyone approves</button></div></div>`;
}
function renderPlan() {
  const el = $('#v-plan'), P = S.session;
  if (!P || S.newPlan) { el.innerHTML = planForm(); return; }
  const R = P.plan, M = S.meta;
  const title = `${R.kind === 'moment' ? 'Moment' : 'Day out'} · ${niceDate(R.date)} · ${R.start}`;
  const phaseChip = { swiping: `<span class="pill sun">Swiping · ${P.round >= M.max_rounds ? 'final round' : 'round ' + P.round + ' of ' + M.max_rounds}</span>`, planning: '<span class="pill sky">Planning</span>',
    approved: '<span class="pill">Approved ✓</span>', ended: '<span class="pill fail">Ended</span>' }[P.phase];
  const people = Object.entries(P.members).map(([n, s]) => `<span class="person ${s.status} ${s.approved ? 'approved' : ''}">${capHtml(n, true)}${esc(n)}${n === P.pitcher ? ' · pitched' : ''}${s.status === 'in' ? (s.approved ? ' ✓✓' : ' ✓') : s.status === 'asked' ? ' · to swipe' : ''}</span>`).join('');
  const head = `<div class="hero"><div class="row"><h2 class="grow">${esc(title)}</h2>${phaseChip}</div>
    ${R.status === 'ok' ? `<div class="meta">${R.stops.length} ${R.stops.length === 1 ? 'stop' : 'stops'} · ends about ${R.end} · ~${money(R.total_cost)} each · budget ${esc(R.budget_label)}${R.budget_cap ? ' (' + money(R.budget_cap) + ')' : ''}</div>
    <div class="row"><button class="pill ${R.checks.passed === R.checks.total ? '' : 'fail'}" data-act="go-inspect">Checks ${R.checks.passed}/${R.checks.total} ›</button><a class="pill sky" href="${esc(R.map_url)}" target="_blank" rel="noopener noreferrer" style="text-decoration:none">Route in Maps ›</a></div>` : ''}</div>`;
  const top = `<div class="head"><span class="muted small grow">Plan #${P.id}${R.run_id ? ' · run #' + R.run_id : ''} · seed ${R.seed}</span><button class="btn small" data-act="new-plan">New plan</button><button class="btn small" data-act="rerun">Run again</button></div>`;
  if (R.status !== 'ok') {
    el.innerHTML = `<div class="stack">${top}${head}<div class="card"><h3>${esc(R.message)}</h3><p class="muted" style="margin-top:6px">Nothing was relaxed to force a plan, and the message never says whose limit blocked it. Inspect shows how many places survived each filter.</p>
      <button class="btn wide" data-act="go-inspect" style="margin-top:10px">Open Inspect</button></div></div>`;
    return;
  }
  const round = P.rounds[P.rounds.length - 1];
  const changes = round && round.changes.length ? `<div class="card flat"><h3>What changed for round ${round.round}</h3>${round.changes.map(c => `<div class="change"><span class="chip tiny sun">${esc(c.kind)}</span>${c.from !== undefined ? `<span><s class="muted">${esc(c.from ?? '')}</s> → <b>${esc(c.to ?? 'removed')}</b></span>` : ''}<span class="muted">${esc(c.why || c.note || '')}</span></div>`).join('')}
    <div class="muted small" style="margin-top:4px">The pod sees what changed, never who asked.</div></div>` : '';
  const edits = P.edits.length ? `<div class="card flat"><h3>Since you last looked</h3>${P.edits.slice(-6).map(c => `<div class="change"><span class="chip tiny sky hub">${esc(c.kind)}</span><span>${c.from ? `<s class="muted">${esc(c.from)}</s> → ` : ''}<b>${esc(c.to ?? 'removed')}</b></span><span class="muted">by ${esc(c.by)}${c.tag ? ' · ' + esc(c.tag) : ''}</span></div>`).join('')}</div>` : '';
  const banner = P.phase === 'approved' ? `<div class="note pea"><b>✓ It's on.</b> ${esc(P.message)}</div>` : P.phase === 'ended' ? `<div class="note coral"><b>Ended.</b> ${esc(P.message)}</div>` : '';
  const leave = R.leave_home.filter(m => m.modes).map(m => `<tr><td><b>${esc(m.name)}</b><br><span class="muted">${m.km} km</span></td>${['walk', 'transit', 'car', 'cab'].map(k => `<td class="num ${k === 'walk' && m.modes[k].minutes > 60 ? 'muted' : ''}">${m.modes[k].leave}<br><span class="muted">${m.modes[k].minutes} min</span></td>`).join('')}</tr>`).join('');
  const history = P.rounds.filter(r => Object.keys(r.votes).length).map(r => `<div class="change"><span class="chip tiny">Round ${r.round}</span><span>${Object.entries(r.votes).map(([n, v]) => `${esc(n)}: <b>${esc(v.answer === 'no_answer' ? 'no answer' : v.answer)}</b>${v.reason ? ' (' + esc(reasonLabel(v.reason)) + ')' : ''}`).join(' · ')}</span></div>`).join('');
  el.innerHTML = `<div class="stack">${top}${head}
    <div class="people">${people}</div>${banner}${changes}${edits}
    <div>${R.stops.map(s => stopCard(s, P)).join('')}</div>
    ${P.phase === 'swiping' ? votePanel(P) : P.phase === 'planning' ? planningPanel(P) : ''}
    <details class="group"><summary>When to leave home</summary><div class="body"><div class="muted small">To reach stop 1 by ${R.start}.</div><div class="scroll-x"><table><thead><tr><th>Pea</th><th class="num">Walk</th><th class="num">Public</th><th class="num">Car</th><th class="num">Cab</th></tr></thead><tbody>${leave || '<tr><td colspan="5" class="muted">No saved homes.</td></tr>'}</tbody></table></div></div></details>
    ${history ? `<details class="group"><summary>How the rounds went</summary><div class="body">${history}<div class="muted small" style="margin-top:6px">Reasons are shown here for testing. In the app only Peapod sees them.</div></div></details>` : ''}
    <div class="card"><div class="row"><h3 class="grow">Score this plan (tester)</h3><span class="muted small" id="fb-status"></span></div>
      <div class="row score" style="margin-top:8px" role="radiogroup" aria-label="Plan score 1 to 5">${[1, 2, 3, 4, 5].map(n => `<button class="${S.fb.plan_score === n ? 'on' : ''}" data-act="score" data-v="${n}">${n}</button>`).join('')}</div>
      <input data-fb="plan_note" value="${esc(S.fb.plan_note)}" placeholder="Anything about the plan as a whole" aria-label="Plan note" style="width:100%;margin-top:8px"></div>
  </div>`;
}

/* ---------- Inspect ---------- */
function funnelHtml(rows) {
  const max = Math.max(1, ...rows.map(r => r.count));
  return rows.map(r => `<div class="bar-row"><span>${esc(r.label)}</span><span class="bar"><i style="width:${(100 * r.count / max).toFixed(1)}%"></i></span><span class="mono" style="text-align:right">${r.count.toLocaleString()}</span></div>`).join('');
}
function partCell(v) { return `<td class="num ${v < 0 ? 'neg' : v > 0 ? 'pos' : 'muted'}">${!v ? '·' : v.toFixed(2)}</td>`; }
function topTable(rows) {
  return `<div class="scroll-x"><table><thead><tr><th>#</th><th>Place</th><th class="num">Score</th>${PARTS.map(p => `<th class="num">${p[1]}</th>`).join('')}<th class="num">Share</th><th class="num">km</th><th>Matched</th></tr></thead><tbody>
    ${rows.map(r => `<tr class="${r.chosen ? 'chosen' : ''}"><td class="num">${r.rank}</td><td style="min-width:170px"><b>${esc(r.place.name)}</b><br><span class="muted">${esc(r.place.hub)} · ~${money(r.place.price_est)} · ${r.arrival}<br>${r.place.chips.map(esc).join(', ') || 'no chip'}</span></td>
      <td class="num"><b>${r.score.toFixed(2)}</b></td>${PARTS.map(p => partCell(r.parts[p[0]])).join('')}
      <td class="num">${Math.round(r.share * 100)}%</td><td class="num">${r.km}</td><td style="min-width:140px">${r.matched.map(m => `${esc(m.name)} <span class="muted">(${m.level === 'hub' ? 'kind' : m.level})</span>`).join(', ') || '<span class="muted">nobody</span>'}</td></tr>`).join('')}</tbody></table></div>`;
}
function renderInspect() {
  const el = $('#v-inspect'), P = S.session;
  if (!P) { el.innerHTML = '<div class="empty-state"><h2>Nothing to inspect yet</h2><p>Plan something first.</p></div>'; return; }
  const R = P.plan, D = R.debug, hubMax = Math.max(1, ...Object.values(D.hub_counts));
  const checks = R.status === 'ok' ? `<div class="card"><div class="head"><h3 class="grow">Sanity checks</h3><span class="pill ${R.checks.passed === R.checks.total ? '' : 'fail'}">${R.checks.passed}/${R.checks.total}</span></div>
    ${R.checks.items.map(c => `<div class="check ${c.pass ? '' : 'fail'}"><b>${c.pass ? '✓' : '✕'}</b><span>${esc(c.label)}<small>${esc(c.detail)}</small></span></div>`).join('')}</div>` : `<div class="note coral">${esc(R.message)}</div>`;
  const limits = `<div class="card"><h3>Each pea's limits</h3><div class="scroll-x"><table><thead><tr><th>Pea</th><th>How far</th><th class="num">Limit</th><th class="num">Reach</th><th class="num">Furthest stop</th></tr></thead><tbody>
    ${D.limits.map(l => { const lh = (R.leave_home || []).find(x => x.name === l.name) || {}; return `<tr><td><b>${esc(l.name)}</b></td><td>${esc(label(S.meta.travel_prefs, l.travel))}</td><td class="num">${l.minutes === null ? 'none' : l.minutes + ' min'}</td><td class="num">${l.km === null ? '–' : l.km + ' km'}</td><td class="num ${l.minutes !== null && lh.furthest_min > l.minutes ? 'neg' : ''}">${lh.furthest_min !== undefined ? lh.furthest_min + ' min' : '–'}</td></tr>`; }).join('')}</tbody></table></div>
    <div class="muted small" style="margin-top:6px">Reach is the straight-line distance the fastest way covers in that time. Plan styles in this pod: ${Object.entries(D.styles).filter(([, v]) => v).map(([k, v]) => `${esc(label(S.meta.styles, k))} ${Math.round(v * 100)}%`).join(', ') || 'none'}.</div></div>`;
  const cov = D.coverage.length ? `<div class="card"><h3>Which peas each stop matched</h3><div class="scroll-x"><table><thead><tr><th>Pea</th>${R.stops.map(s => `<th>${s.index + 1}. ${esc(s.place.name.slice(0, 16))}</th>`).join('')}<th>Served</th></tr></thead><tbody>
    ${D.coverage.map(c => `<tr><td><b>${esc(c.name)}</b></td>${c.stops.map(l => `<td>${l ? `<span class="chip tiny ${l}">${l === 'hub' ? 'kind' : l === 'tile' ? 'interest' : 'favourite'}</span>` : '<span class="muted">·</span>'}</td>`).join('')}<td>${c.stops.some(l => l === 'exact' || l === 'tile') ? '✓' : '<span style="color:var(--coral-text)">no match</span>'}</td></tr>`).join('')}</tbody></table></div></div>` : '';
  const stops = D.per_stop.map(ps => {
    const st = R.stops.find(s => s.place.name === (ps.top.find(t => t.chosen) || {}).place?.name);
    const basis = st ? `<details class="more"><summary>Where this place's data came from</summary><div class="chips" style="margin-top:6px">${Object.entries(st.place.basis || {}).map(([k, v]) => `<span class="chip tiny ${v === 'estimated' ? 'tile' : v === 'unknown' || v === 'none' ? 'dim' : 'exact'}">${esc(k)}: ${esc(v)}</span>`).join('')}</div></details>` : '';
    return `<details class="group"><summary>Stop ${ps.index + 1}${st ? ' · ' + esc(st.place.name) : ''} ${ps.is_new_slot ? '<span class="chip tiny sun">new slot</span>' : ''}${ps.kept ? '<span class="chip tiny">kept</span>' : ''}${ps.replaced ? '<span class="chip tiny coral">replaced ' + esc(ps.replaced) + '</span>' : ''}${ps.loosened_hub_mix ? '<span class="chip tiny tile">kind mix loosened</span>' : ''}</summary><div class="body">
      <div class="muted small" style="margin-bottom:8px">${esc(ps.slot)}: ${ps.allowed_hubs.map(esc).join(', ') || 'none'}</div>
      ${funnelHtml(ps.funnel)}
      ${ps.top.length ? `<div class="label" style="margin:12px 0 4px">Top ${ps.top.length} candidates · score in parts</div>${topTable(ps.top)}` : ''}${basis}</div></details>`;
  }).join('');
  el.innerHTML = `<div class="stack">
    <div class="head"><h2 class="grow">Inspect · plan #${P.id}</h2></div>
    ${(D.notes || []).map(n => `<div class="note">${esc(n)}</div>`).join('')}
    ${checks}
    ${R.status === 'ok' ? '<div class="card"><h3>Map</h3><div id="map"></div><div class="muted small" style="margin-top:6px">Green pins are stops in order; blue dots are homes.</div></div>' : ''}
    <div class="kv"><div><span class="label">Lowest budget</span><b>${esc(R.budget_label)}</b>${R.budget_cap ? 'limit ' + money(R.budget_cap) : 'no limit'}</div><div><span class="label">Price target / stop</span><b>${money(D.price_target_per_stop)}</b></div>
      <div><span class="label">Everyone over 18</span><b>${D.all_over_18 ? 'Yes' : 'No'}</b></div><div><span class="label">Kinds wanted</span><b style="font-size:13px">${D.wanted_hubs.map(esc).join(', ') || 'none'}</b></div></div>
    <div class="two"><div class="card"><h3>Filter: what survived each hard limit</h3><div style="margin-top:8px">${funnelHtml(D.funnel)}</div></div>
      <div class="card"><h3>Eligible places per kind</h3><div class="muted small">Fewer than 3 is "empty".</div><div style="margin-top:8px">
      ${Object.entries(D.hub_counts).map(([h, n]) => `<div class="bar-row ${D.empty_hubs.includes(h) ? 'empty' : ''}"><span>${esc(h)}${D.empty_hubs.includes(h) ? ' <span class="chip tiny coral">empty</span>' : ''}</span><span class="bar"><i style="width:${(100 * n / hubMax).toFixed(1)}%"></i></span><span class="mono" style="text-align:right">${n.toLocaleString()}</span></div>`).join('')}</div></div></div>
    ${limits}${cov}${stops}
  </div>`;
  drawMap();
}
let map = null;
function drawMap() {
  const el = $('#map'), R = S.session?.plan;
  if (map) { map.remove(); map = null; }
  if (!el || !R || R.status !== 'ok' || document.body.dataset.view !== 'inspect') return;
  if (!window.L) { el.outerHTML = '<div class="muted small">The map library did not load. Use "Route in Maps" on the plan.</div>'; return; }
  map = L.map(el, { scrollWheelZoom: false });
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap contributors' }).addTo(map);
  const pts = R.stops.map(s => [s.place.lat, s.place.lng]);
  R.stops.forEach((s, i) => L.marker(pts[i], { icon: L.divIcon({ className: '', html: `<div class="map-pin">${i + 1}</div>`, iconSize: [26, 26], iconAnchor: [13, 13] }) }).addTo(map).bindTooltip(`${i + 1}. ${s.place.name} · ${s.arrival}`));
  if (pts.length > 1) L.polyline(pts, { color: '#1E3A26', weight: 3, dashArray: '6 6' }).addTo(map);
  const all = pts.slice();
  (S.session.pod.members || []).forEach(m => {
    const h = m.home || {}, c = h.lat !== undefined ? [Number(h.lat), Number(h.lng)] : S.meta.zone_centroids[h.zone];
    if (!c || !isFinite(c[0]) || !isFinite(c[1])) return;
    L.marker(c, { icon: L.divIcon({ className: '', html: '<div class="map-home"></div>', iconSize: [12, 12], iconAnchor: [6, 6] }) }).addTo(map).bindTooltip(m.name + ' (home)');
    all.push(c);
  });
  map.fitBounds(L.latLngBounds(pts.length > 1 ? pts : all).pad(0.25), { maxZoom: 15 });
}

/* ---------- Tune ---------- */
function renderTune() {
  const M = S.meta, C = S.cmp;
  if (!C.a) C.a = { ...S.weights }; if (!C.b) C.b = { ...S.weights };
  const groups = [...new Set(M.weights.map(w => w.group))];
  const groupHtml = groups.map((g, gi) => {
    const ws = M.weights.filter(w => w.group === g), changed = ws.filter(w => S.weights[w.key] !== w.default).length;
    return `<details class="group" ${gi === 0 ? 'open' : ''}><summary>${esc(g)} ${changed ? `<span class="pill fail">${changed} changed</span>` : ''}</summary><div class="body">
      ${ws.map(w => `<div class="weight ${S.weights[w.key] !== w.default ? 'changed' : ''}"><span class="name">${esc(w.label)}</span>
        <input type="number" data-w="${w.key}" value="${S.weights[w.key]}" min="${w.min}" max="${w.max}" step="${w.step}" inputmode="decimal" aria-label="${esc(w.label)}">
        <input type="range" data-w="${w.key}" value="${S.weights[w.key]}" min="${w.min}" max="${w.max}" step="${w.step}" style="grid-column:1/-1" aria-label="${esc(w.label)} slider">
        <span class="help">${esc(w.help)} Default ${w.default}.</span></div>`).join('')}</div></details>`;
  }).join('');
  let out = '';
  if (C.out) {
    const A = C.out.a, B = C.out.b, n = Math.max(A.stops.length, B.stops.length);
    const sum = (R, name) => `<div class="card"><h3>Set ${name}</h3>${R.status !== 'ok' ? `<div class="note coral" style="margin-top:6px">${esc(R.message)}</div>` : `<div class="muted small">~${money(R.total_cost)} each · ends ${R.end} · <span class="pill ${R.checks.passed === R.checks.total ? '' : 'fail'}">checks ${R.checks.passed}/${R.checks.total}</span></div>
      ${R.checks.items.filter(c => !c.pass).map(c => `<div class="note coral" style="margin-top:6px">${esc(c.label)}: ${esc(c.detail)}</div>`).join('')}`}</div>`;
    const cell = (s, o) => !s ? '<td class="muted">—</td>' : `<td class="${o && o.place.id === s.place.id ? '' : 'diff'}" style="min-width:150px"><span class="mono">${s.arrival}</span> <b>${esc(s.place.name)}</b><br><span class="muted">${esc(s.place.hub)} · ~${money(s.price_est)} · ${s.score.toFixed(2)}</span></td>`;
    const same = A.stops.filter((s, i) => B.stops[i] && B.stops[i].place.id === s.place.id).length;
    out = `<div class="two">${sum(A, 'A')}${sum(B, 'B')}</div><div class="card"><div class="head"><h3 class="grow">Stops side by side</h3><span class="pill sun">${same} of ${n} the same</span></div>
      <div class="scroll-x"><table><thead><tr><th>#</th><th>Set A</th><th>Set B</th></tr></thead><tbody>${Array.from({ length: n }, (_, i) => `<tr><td class="num">${i + 1}</td>${cell(A.stops[i], B.stops[i])}${cell(B.stops[i], A.stops[i])}</tr>`).join('')}</tbody></table></div></div>`;
  }
  const diff = M.weights.filter(w => C.a[w.key] !== C.b[w.key]);
  $('#v-tune').innerHTML = `<div class="stack">
    <div class="head"><h2 class="grow">Tune the rules</h2><button class="btn small" data-act="reset-weights">Reset</button></div>
    <div class="row end"><label class="field"><span class="label">Random seed</span><input type="number" data-seed value="${S.seed}" step="1" inputmode="numeric"></label><button class="btn small" data-act="new-seed" style="min-height:42px">New seed</button></div>
    <div class="muted small">The same pod, request, weights and seed always give the same plan.</div>
    ${groupHtml}
    <details class="group"><summary>Budget tiers</summary><div class="body"><div class="muted small" style="margin-bottom:8px">Whole day, SGD per person. The real values are not decided.</div>
      <div class="row end"><label class="field"><span class="label">Keep it low is under</span><input type="number" data-cut="0" value="${S.tierCuts[0]}" min="1" step="5" inputmode="numeric"></label>
      <label class="field"><span class="label">Splurge starts at</span><input type="number" data-cut="1" value="${S.tierCuts[1]}" min="2" step="5" inputmode="numeric"></label></div></div></details>
    <button class="btn primary wide" data-act="rerun">Run again with these weights</button>
    <details class="group" ${C.out ? 'open' : ''}><summary>Compare two weight sets</summary><div class="body stack">
      <div class="muted small">Same pod and request, two sets of weights, first drafts only. ${diff.length ? 'Different now: ' + diff.map(w => `${esc(w.label)} (${C.a[w.key]} vs ${C.b[w.key]})`).join(', ') + '.' : 'The two sets are the same right now.'}</div>
      <div class="row"><button class="btn small grow" data-act="to-a">Save current as A</button><button class="btn small grow" data-act="to-b">Save current as B</button></div>
      <div class="row"><button class="btn small grow" data-act="load-a">Load A to edit</button><button class="btn small grow" data-act="load-b">Load B to edit</button></div>
      <button class="btn wide" data-act="run-compare">Run A and B</button>${out}</div></details>
  </div>`;
}

/* ---------- Log ---------- */
async function renderLog() {
  const el = $('#v-log'), tab = S.logTab;
  const tabs = seg([{ key: 'events', label: "This plan's log" }, { key: 'rules', label: 'Rules' }, { key: 'runs', label: 'All runs' }], tab, 'data-act="log-tab"');
  let body = '';
  if (tab === 'events') {
    const ev = S.session?.events || [];
    body = !S.session ? '<div class="empty-state"><h2>No plan yet</h2><p>The log fills as a plan is requested, swiped, reworked and approved.</p></div>' : `<div class="card"><div class="head"><h3 class="grow">Plan #${S.session.id} · ${ev.length} events</h3><a class="btn small" style="display:inline-grid;place-items:center;text-decoration:none" href="/api/export.csv?level=events">Export all events</a></div>
      <div class="muted small" style="margin:4px 0">Append only. Tap an event for everything that was recorded.</div>
      ${ev.map(e => `<details class="event"><summary style="display:contents;cursor:pointer"><span class="when">${esc(e.at.slice(11, 16))}<br>R${e.round ?? '-'}</span><span><span class="chip tiny ${e.type === 'vote' || e.type === 'no_answer' ? 'sun' : e.type === 'rework' || e.type === 'plan_built' ? 'exact' : e.type === 'taste_nudge' ? 'coral' : ''}">${esc(e.type.replace(/_/g, ' '))}</span> ${e.actor ? '<b>' + esc(e.actor) + '</b> · ' : ''}${esc(e.summary)}</span></summary><span></span><pre>${esc(JSON.stringify(e.data, null, 1))}</pre></details>`).join('')}</div>`;
  } else if (tab === 'rules') {
    if (!S.rules) { try { S.rules = (await api('/api/rules')).rules; } catch (e) { return toast(e.message, true); } }
    const stages = [...new Set(S.rules.map(r => r.stage))];
    body = `<div class="note">Every rule the engine applies. <b>manual</b> = from the engine manual, <b>design</b> = from the app design, <b>guess</b> = my choice where neither says. Tune names match the Tune tab.</div>
      ${stages.map((st, i) => `<details class="group" ${i < 2 ? 'open' : ''}><summary>${esc(st)} <span class="pill grey">${S.rules.filter(r => r.stage === st).length}</span></summary><div class="body">
      ${S.rules.filter(r => r.stage === st).map(r => `<div class="rule"><span class="id">${esc(r.id)}</span>${esc(r.rule)}<div style="margin-top:4px"><span class="chip tiny ${r.source.includes('guess') ? 'tile' : 'exact'}">${esc(r.source)}</span>${r.tune ? ` <span class="chip tiny dim">tune: ${esc(r.tune)}</span>` : ''}</div></div>`).join('')}</div></details>`).join('')}`;
  } else {
    if (!S.runs) { try { S.runs = await api('/api/runs'); } catch (e) { return toast(e.message, true); } }
    const D = S.runs, st = D.stats, pct = st.checks_total ? Math.round(100 * st.checks_passed / st.checks_total) : null, v = st.verdicts || {};
    body = `<div class="kv"><div><span class="label">Plans built</span><b>${st.runs}</b>${st.planned} found a plan</div><div><span class="label">Checks passed</span><b>${pct === null ? '–' : pct + '%'}</b>${st.clean_runs} clean</div>
      <div><span class="label">Avg plan score</span><b>${st.avg_plan_score ?? '–'}</b>${st.scored_runs} scored</div><div><span class="label">Stops rated</span><b style="font-size:14px">${v.good || 0} good · ${v.ok || 0} OK · ${v.bad || 0} bad</b></div></div>
      <div class="row"><a class="btn small grow" style="display:inline-grid;place-items:center;text-decoration:none" href="/api/export.csv?level=stops">CSV · per stop</a><a class="btn small grow" style="display:inline-grid;place-items:center;text-decoration:none" href="/api/export.csv?level=runs">CSV · per run</a><a class="btn small grow" style="display:inline-grid;place-items:center;text-decoration:none" href="/api/export.csv?level=events">CSV · log</a></div>
      <div class="card"><div class="scroll-x"><table><thead><tr><th>Run</th><th>When</th><th>Request</th><th class="num">Checks</th><th class="num">Score</th><th></th></tr></thead><tbody>
      ${D.runs.map(r => `<tr><td class="num">${r.id}</td><td class="mono">${esc(r.created_at.slice(5, 16).replace('T', ' '))}<br><span class="muted">${esc(r.tester || '')}</span></td>
        <td>${r.kind === 'moment' ? 'Moment' : 'Day out'} · ${esc(niceDate(r.request.date))}<br><span class="muted">${esc(r.label || '')}</span></td>
        <td class="num ${r.status !== 'ok' || r.checks_passed < r.checks_total ? 'neg' : 'pos'}">${r.status === 'ok' ? r.checks_passed + '/' + r.checks_total : 'no plan'}</td>
        <td class="num">${r.plan_score ?? (r.has_feedback ? '•' : '')}</td><td>${r.session_id ? `<button class="btn small" data-act="open-session" data-v="${r.session_id}">Open</button>` : ''}</td></tr>`).join('') || '<tr><td colspan="6" class="muted">No runs yet.</td></tr>'}</tbody></table></div></div>`;
  }
  el.innerHTML = `<div class="stack"><div class="head"><h2 class="grow">Log</h2></div>${tabs}${body}</div>`;
}

/* ---------- session handling ---------- */
function renderAll() { renderPlan(); renderInspect(); if (document.body.dataset.view === 'log') renderLog(); }
function setSession(P, keepFb) {
  S.session = P; S.newPlan = false; S.runs = null;
  const going = Object.entries(P.members).filter(([, s]) => s.status === 'in').map(([n]) => n);
  if (!going.includes(S.actor)) S.actor = going[0] || '';
  S.votes = {};
  if (!keepFb || S.fbRun !== P.plan.run_id) { S.fb = { plan_score: null, plan_note: '', stops: {} }; S.fbRun = P.plan.run_id; }
  // what Peapod learned in this plan carries over to the pod, so the next plan reflects it
  let learned = false;
  (P.pod.members || []).forEach(pm => { const m = S.pod.members.find(x => x.name === pm.name); if (m && pm.taste && JSON.stringify(m.taste || {}) !== JSON.stringify(pm.taste)) { m.taste = pm.taste; learned = true; } });
  if (learned) renderPod();
  save(); renderAll();
}
async function startPlan() {
  const probs = podProblems();
  if (probs.length) { setView('pod'); renderPod(); return toast(probs[0], true); }
  if (S.busy) return; S.busy = true; toast('Planning…');
  try {
    const P = await api('/api/session', { pod: S.pod, request: S.req, config: config(), pitcher: S.pitcher || null, tester: S.tester, label: S.label });
    setSession(P); setView('plan');
    toast(P.plan.status === 'ok' ? `Planned · checks ${P.plan.checks.passed}/${P.plan.checks.total}` : 'No plan fits', P.plan.status !== 'ok');
  } catch (e) { toast(e.message, true); }
  S.busy = false;
}
async function act(body, okMsg) {
  if (S.busy) return; S.busy = true;
  try { const P = await api(`/api/session/${S.session.id}/act`, body); setSession(P, true); if (okMsg) toast(okMsg); }
  catch (e) { toast(e.message, true); }
  S.busy = false;
}
let fbTimer = null;
function saveFeedback() {
  const run = S.session?.plan?.run_id; if (!run) return;
  clearTimeout(fbTimer);
  fbTimer = setTimeout(async () => {
    try {
      await api(`/api/runs/${run}/feedback`, { plan_score: S.fb.plan_score, plan_note: S.fb.plan_note, stops: Object.entries(S.fb.stops).map(([i, s]) => ({ index: Number(i), ...s })) });
      const st = $('#fb-status'); if (st) st.textContent = 'Saved'; S.runs = null;
    } catch (e) { toast(e.message, true); }
  }, 400);
}
function optionSheet(title, opts, onPick) {
  sheet(`<div class="stack"><div class="head"><h3 class="grow">${esc(title)}</h3><button class="btn small" data-act="close-sheet">Close</button></div>
    ${opts.length ? opts.map((o, i) => `<button class="option" data-opt="${i}"><span class="chip tiny sun">${esc(o.tag)}</span><b>${esc(o.place.name)}</b><span class="muted small">${esc([...new Set([o.fact, o.place.hub])].join(' · '))} · ~${money(o.place.price_est)} each</span></button>`).join('') : '<div class="note">Nothing else fits everyone\'s limits here.</div>'}</div>`);
  $$('#sheet [data-opt]').forEach(b => b.addEventListener('click', () => { closeSheet(); onPick(opts[Number(b.dataset.opt)]); }));
}

/* ---------- events ---------- */
document.addEventListener('click', async e => {
  if (e.target.id === 'sheet') return closeSheet();
  const nav = e.target.closest('.tabs button'); if (nav) return setView(nav.dataset.view);
  const b = e.target.closest('[data-act]'); if (!b) return;
  const a = b.dataset.act, i = Number(b.dataset.i), v = b.dataset.v, n = b.dataset.n, m = S.pod.members[i];
  switch (a) {
    case 'add-member': S.pod.members.push(newMember(S.pod.members.length)); S.openMember = S.pod.members.length - 1; renderPod(); renderPlan(); break;
    case 'rm-member': S.pod.members.splice(i, 1); S.openMember = -1; if (!S.pod.members.some(x => x.name === S.pitcher)) S.pitcher = ''; renderPod(); renderPlan(); break;
    case 'tile': {
      const at = m.interests.indexOf(v);
      if (at >= 0) { m.interests.splice(at, 1); const chips = tile(v).chips.map(c => c.name); m.favourites = m.favourites.filter(c => !chips.includes(c)); }
      else if (m.interests.length >= 5) return toast('Up to 5 interests', true); else m.interests.push(v);
      S.openMember = i; renderPod(); break;
    }
    case 'fav': { const c = b.dataset.chip, at = m.favourites.indexOf(c); if (at >= 0) m.favourites.splice(at, 1); else m.favourites.push(c); S.openMember = i; renderPod(); break; }
    case 'mset': m[b.dataset.f] = v; S.openMember = i; renderPod(); break;
    case 'reset-taste': delete m.taste; S.openMember = i; renderPod(); toast('Learned taste forgotten'); break;
    case 'random-pod': try { S.pod = await api('/api/random-pod'); S.openMember = -1; S.pitcher = ''; renderPod(); renderPlan(); } catch (err) { toast(err.message, true); } break;
    case 'go-plan': S.newPlan = true; renderPlan(); setView('plan'); break;
    case 'go-inspect': setView('inspect'); break;
    case 'kind': S.req.kind = v; renderPlan(); save(); break;
    case 'surprise': Object.assign(S.req, { kind: 'dayout', area: '', budget: '', hub: '' }); S.pitcher = ''; save(); startPlan(); break;
    case 'plan': case 'rerun': startPlan(); break;
    case 'new-plan': S.newPlan = true; renderPlan(); scrollTo({ top: 0 }); break;
    case 'back-plan': S.newPlan = false; renderPlan(); break;
    case 'answer': S.votes[n] = { answer: v, reason: v === (S.votes[n] || {}).answer ? (S.votes[n] || {}).reason : '' }; renderPlan(); break;
    case 'reason': S.votes[n].reason = S.votes[n].reason === v ? '' : v; renderPlan(); break;
    case 'all-in': Object.entries(S.session.members).forEach(([name, st]) => { if (st.status === 'asked') S.votes[name] = { answer: 'in' }; }); renderPlan(); break;
    case 'close-round': {
      if (S.busy) return; S.busy = true;
      const votes = Object.fromEntries(Object.entries(S.votes).filter(([, x]) => x.answer).map(([k, x]) => [k, { answer: x.answer, reason: x.reason || null }]));
      try {
        const before = S.session.round, P = await api(`/api/session/${S.session.id}/votes`, { votes });
        setSession(P);
        toast(P.phase === 'planning' ? "It's a plan" : P.phase === 'ended' ? 'The plan ended' : P.round > before ? `Round ${P.round}: ${P.rounds[P.rounds.length - 1].changes.length} change(s)` : 'Round closed');
        scrollTo({ top: 0 });
      } catch (err) { toast(err.message, true); }
      S.busy = false; break;
    }
    case 'approve': act({ type: 'approve', name: n }); break;
    case 'unapprove': act({ type: 'unapprove', name: n }); break;
    case 'approve-all': {
      for (const [name, st] of Object.entries(S.session.members)) if (st.status === 'in' && !st.approved && S.session.phase === 'planning') await act({ type: 'approve', name });
      break;
    }
    case 'rejoin': act({ type: 'rejoin', name: n }, n + ' is back in'); break;
    case 'leave': {
      const all = [...S.meta.not_for_me_reasons, ...S.meta.practical_reasons];
      sheet(`<div class="stack"><div class="head"><h3 class="grow">${esc(n)} is leaving. Why?</h3><button class="btn small" data-act="close-sheet">Close</button></div>
        <div class="muted small">The plan stays as it is. "Not for me" reasons nudge their taste; practical ones do not.</div>
        ${all.map(r => `<button class="option" data-leave="${r.key}"><b style="margin:0">${esc(r.label)}</b></button>`).join('')}<button class="option" data-leave=""><b style="margin:0">No reason</b></button></div>`);
      $$('#sheet [data-leave]').forEach(x => x.addEventListener('click', () => { closeSheet(); act({ type: 'leave', name: n, reason: x.dataset.leave || null }, n + ' left'); }));
      break;
    }
    case 'heart': act({ type: 'heart', name: S.actor, stop: i }); break;
    case 'move': act({ type: 'move', name: S.actor, stop: i, dir: v }); break;
    case 'remove': act({ type: 'remove', name: S.actor, stop: i }, 'Stop removed'); break;
    case 'change': try {
      toast('Finding options…');
      const { options } = await api(`/api/session/${S.session.id}/options?stop=${i}`);
      optionSheet('Change it to', options, o => act({ type: 'change', name: S.actor, stop: i, place_id: o.place.id, tag: o.tag }, 'Stop changed'));
    } catch (err) { toast(err.message, true); } break;
    case 'add-stop': try {
      toast('Finding quick picks…');
      const { options } = await api(`/api/session/${S.session.id}/options`);
      optionSheet('Add a stop at the end of the day', options, o => act({ type: 'add', name: S.actor, place_id: o.place.id }, 'Stop added'));
    } catch (err) { toast(err.message, true); } break;
    case 'close-sheet': closeSheet(); break;
    case 'verdict': { const f = S.fb.stops[i] = S.fb.stops[i] || {}; f.verdict = f.verdict === v ? '' : v; b.parentElement.querySelectorAll('button').forEach(x => { x.className = x.dataset.v === f.verdict ? 'on ' + ({ good: 'in', ok: 'maybe', bad: 'cant' }[x.dataset.v]) : ''; }); saveFeedback(); break; }
    case 'score': S.fb.plan_score = S.fb.plan_score === Number(v) ? null : Number(v); b.parentElement.querySelectorAll('button').forEach(x => x.classList.toggle('on', Number(x.dataset.v) === S.fb.plan_score)); saveFeedback(); break;
    case 'reset-weights': S.weights = defaultWeights(); renderTune(); save(); break;
    case 'new-seed': S.seed = Math.floor(Math.random() * 100000); renderTune(); renderPlan(); save(); break;
    case 'to-a': S.cmp.a = { ...S.weights }; S.cmp.seedA = S.seed; renderTune(); save(); toast('Saved as set A'); break;
    case 'to-b': S.cmp.b = { ...S.weights }; S.cmp.seedB = S.seed; renderTune(); save(); toast('Saved as set B'); break;
    case 'load-a': S.weights = { ...defaultWeights(), ...S.cmp.a }; S.seed = S.cmp.seedA; renderTune(); save(); toast('Editing set A. Save it as A when done.'); break;
    case 'load-b': S.weights = { ...defaultWeights(), ...S.cmp.b }; S.seed = S.cmp.seedB; renderTune(); save(); toast('Editing set B. Save it as B when done.'); break;
    case 'run-compare': {
      const probs = podProblems(); if (probs.length) return toast(probs[0], true);
      b.disabled = true; toast('Running both…');
      try { S.cmp.out = await api('/api/compare', { pod: S.pod, request: S.req, config_a: config(S.cmp.a, S.cmp.seedA), config_b: config(S.cmp.b, S.cmp.seedB), tester: S.tester, label: S.label }); S.runs = null; }
      catch (err) { toast(err.message, true); }
      renderTune(); break;
    }
    case 'log-tab': S.logTab = v; renderLog(); break;
    case 'open-session': try {
      const P = await api('/api/session/' + v);
      S.pod = P.pod; S.req = Object.assign({ area: '', budget: '', hub: '' }, P.request); S.pitcher = P.pitcher || '';
      S.weights = Object.assign(defaultWeights(), P.config.weights); S.seed = P.config.seed;
      renderPod(); renderTune(); setSession(P); setView('plan'); toast('Plan #' + P.id + ' loaded');
    } catch (err) { toast(err.message, true); } break;
  }
});

document.addEventListener('input', e => {
  const t = e.target, d = t.dataset;
  if (d.f) {
    const m = S.pod.members[Number(d.i)];
    if (d.f === 'name') m.name = t.value; else if (d.f === 'needs') m.needs = t.value; else if (d.f === 'lat' || d.f === 'lng') m.home[d.f] = t.value;
    save(); return;
  }
  if (d.r) {
    if (d.r === 'label') S.label = t.value; else if (d.r === 'tester') S.tester = t.value; else if (d.r === 'pitcher') S.pitcher = t.value; else S.req[d.r] = t.value;
    save(); return;
  }
  if (d.w) {
    const spec = S.meta.weights.find(w => w.key === d.w), n = Number(t.value);
    if (t.value === '' || !isFinite(n)) return;
    S.weights[d.w] = Math.min(spec.max, Math.max(spec.min, n));
    $$(`[data-w="${d.w}"]`).forEach(o => { if (o !== t) o.value = S.weights[d.w]; });
    t.closest('.weight').classList.toggle('changed', S.weights[d.w] !== spec.default); save(); return;
  }
  if (d.seed !== undefined) { S.seed = Math.round(Number(t.value)) || 0; save(); return; }
  if (d.fb === 'note') { (S.fb.stops[Number(d.i)] = S.fb.stops[Number(d.i)] || {}).note = t.value; saveFeedback(); return; }
  if (d.fb === 'plan_note') { S.fb.plan_note = t.value; saveFeedback(); }
});

document.addEventListener('change', e => {
  const t = e.target, d = t.dataset;
  if (t.id === 'example' && t.value !== '') { S.pod = JSON.parse(JSON.stringify(S.meta.examples[Number(t.value)])); S.openMember = -1; S.pitcher = ''; renderPod(); renderPlan(); return; }
  if (d.f === 'over18') { S.pod.members[Number(d.i)].over18 = t.checked; save(); return; }
  if (d.f === 'homezone') {
    const m = S.pod.members[Number(d.i)];
    if (t.value === '__c') { const c = S.meta.zone_centroids[m.home.zone] || [1.3521, 103.8198]; m.home = { lat: c[0], lng: c[1] }; } else m.home = { zone: t.value };
    S.openMember = Number(d.i); renderPod(); return;
  }
  if (d.f === 'name') { S.openMember = Number(d.i); renderPod(); renderPlan(); return; }
  if (d.actor !== undefined) { S.actor = t.value; renderPlan(); return; }
  if (d.fb === 'reason') { (S.fb.stops[Number(d.i)] = S.fb.stops[Number(d.i)] || {}).reason = t.value; saveFeedback(); return; }
  if (d.cut !== undefined) {
    S.tierCuts[Number(d.cut)] = Math.max(1, Math.round(Number(t.value)) || 0);
    if (S.tierCuts[1] <= S.tierCuts[0]) S.tierCuts[1] = S.tierCuts[0] + 10;
    renderTune(); renderPod(); renderPlan(); save();
  }
});
document.addEventListener('toggle', e => {
  const d = e.target; if (!d.classList || !d.classList.contains('member')) return;
  if (d.open) S.openMember = Number(d.dataset.i); else if (S.openMember === Number(d.dataset.i)) S.openMember = -1;
}, true);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeSheet(); });

/* ---------- start ---------- */
(async () => {
  try { S.meta = await api('/api/meta'); } catch (e) { return toast(e.message, true); }
  const M = S.meta, saved = load();
  S.weights = defaultWeights(); S.seed = M.seed; S.tierCuts = [M.budget_tiers[0].max, M.budget_tiers[1].max];
  S.req.date = M.defaults.date; S.req.start = M.defaults.start;
  S.pod = JSON.parse(JSON.stringify(M.examples[0]));
  if (saved) {
    if (saved.pod?.members?.length && saved.pod.members.every(m => Array.isArray(m.interests))) S.pod = saved.pod;
    if (saved.req) Object.assign(S.req, saved.req);
    if (!S.req.date || S.req.date < M.defaults.today) S.req.date = M.defaults.date;
    if (saved.weights) M.weights.forEach(w => { if (typeof saved.weights[w.key] === 'number') S.weights[w.key] = saved.weights[w.key]; });
    if (typeof saved.seed === 'number') S.seed = saved.seed;
    if (Array.isArray(saved.tierCuts)) S.tierCuts = saved.tierCuts;
    if (saved.cmp) Object.assign(S.cmp, saved.cmp);
    S.tester = saved.tester || ''; S.label = saved.label || ''; S.pitcher = saved.pitcher || '';
  }
  S.pod.members.forEach(m => { m.favourites = m.favourites || []; m.interests = m.interests || []; });
  $('#dataset-note').title = M.dataset.problem || '';
  $('#dataset-note').textContent = `${M.dataset.places.toLocaleString()} places · ${M.dataset.source}`;
  renderPod(); renderPlan(); renderInspect(); renderTune();
  setView(innerWidth >= 1040 ? 'plan' : 'pod');
  if (saved?.sessionId) { try { setSession(await api('/api/session/' + saved.sessionId)); if (innerWidth < 1040) setView('plan'); } catch (e) { /* the plan is gone (free tier restart): start fresh */ } }
})();
})();
