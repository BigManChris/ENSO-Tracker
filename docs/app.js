"use strict";

/* ---------- helpers ---------- */
const $ = (s) => document.querySelector(s);
const NS = "http://www.w3.org/2000/svg";
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sign = (v, d = 2) => (v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d));
const pct = (p) => `${Math.round(p * 100)}%`;
const SEASONS = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const idx = (label) => { const [y, m] = label.split("-").map(Number); return y * 12 + m - 1; };
const seasonOf = (end) => { const c = end - 1; return `${SEASONS[((c % 12) + 12) % 12]} ${Math.floor(c / 12)}`; };
const Z80 = 1.2816; // half-width of an 80% normal range, in sigmas

async function getJSON(path, fallback) {
  try { const r = await fetch(path, { cache: "no-cache" }); return r.ok ? await r.json() : fallback; }
  catch { return fallback; }
}

function el(tag, attrs = {}, parent) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}
function text(parent, x, y, str, attrs = {}) {
  const t = el("text", { x, y, ...attrs }, parent);
  t.textContent = str;
  return t;
}
const linePath = (pts) => pts.filter((p) => p[1] != null)
  .map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");

/* tooltip */
const tip = $("#tip");
function showTip(evt, html) {
  tip.innerHTML = html;
  tip.hidden = false;
  const pad = 14, r = tip.getBoundingClientRect();
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + r.width > innerWidth - 8) x = evt.clientX - r.width - pad;
  if (y + r.height > innerHeight - 8) y = evt.clientY - r.height - pad;
  tip.style.left = `${x}px`; tip.style.top = `${y}px`;
}
const hideTip = () => { tip.hidden = true; };
const row = (label, value, color, dash) => `<div class="row"><span>${color ? `<i class="sw" style="background:${color}${dash ? ";opacity:.6" : ""}"></i>` : ""}${esc(label)}</span><span>${value}</span></div>`;

function legend(target, items) {
  $(target).innerHTML = items.map(([label, color, kind = ""]) =>
    `<span><i class="${kind}" style="${kind === "box" || kind === "dot" ? "background" : "border-color"}:${color}"></i>${esc(label)}</span>`).join("");
}

function frame(container, height, m = { t: 12, r: 70, b: 34, l: 44 }) {
  const host = $(container);
  host.innerHTML = "";
  const W = Math.max(320, host.clientWidth), H = height;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" }, host);
  return { svg, W, H, m, iw: W - m.l - m.r, ih: H - m.t - m.b };
}

/* ---------- state ---------- */
let FC, OBS, SKILL, SCORE, OFFICIAL, PAST = [];

/* ---------- headline & tiles ---------- */
function renderHeader() {
  const ens = FC.ensemble;
  let peak = 0;
  ens.forEach((v, i) => { if (Math.abs(v) > Math.abs(ens[peak])) peak = i; });
  const cat = FC.category[peak];
  $("#headline").textContent = cat === "Neutral"
    ? "Neither El Niño nor La Niña expected in the coming year"
    : `${cat} expected, peaking around ${FC.seasons[peak]}`;
  $("#subline").textContent = `Forecast made ${FC.made_at.slice(0, 10)} with NOAA data through ${FC.data_through}. Average of three models: analog, linear and a small neural network.`;

  const winter = FC.seasons.findIndex((s) => s.startsWith("DJF"));
  const w = winter >= 0 ? winter : peak;
  const byName = Object.fromEntries(Object.entries(SKILL?.by_model || {}).map(([k, v]) => [k, v]));
  const lead = 6;
  const sk = byName.Ensemble?.[lead - 1], skp = byName.Persistence?.[lead - 1];
  const tiles = [
    ["Latest observed", sign(FC.latest_observed.roni), `${FC.latest_observed.season} · ${strength(FC.latest_observed.roni)}`],
    ["Forecast peak", sign(ens[peak]), `${FC.seasons[peak]} · ${cat}`],
    [`Chance of El Niño in ${FC.seasons[w]}`, pct(FC.probabilities[w].el_nino), `La Niña ${pct(FC.probabilities[w].la_nina)} · neutral ${pct(FC.probabilities[w].neutral)}`],
    [`Back-tested skill, ${lead} seasons ahead`, sk ? sk.corr.toFixed(2) : "–", skp ? `correlation · just assuming no change scores ${skp.corr.toFixed(2)}` : ""],
  ];
  $("#tiles").innerHTML = tiles.map(([l, v, f]) =>
    `<div class="tile"><div class="label">${esc(l)}</div><div class="value">${esc(v)}</div><div class="tfoot">${esc(f)}</div></div>`).join("");
}

function strength(v) {
  const a = Math.abs(v);
  if (a < 0.5) return "Neutral";
  const kind = v > 0 ? "El Niño" : "La Niña";
  return `${a < 1 ? "Weak" : a < 1.5 ? "Moderate" : a < 2 ? "Strong" : "Very strong"} ${kind}`;
}

/* ---------- main plume chart ---------- */
function renderPlume() {
  plume({ sel: "#plume", legend: "#plume-legend", fc: FC, official: OFFICIAL, showPast: $("#show-past").checked });
}

function plume(opts) {
  const { fc: FC, official: OFFICIAL } = opts;
  const M = idx(FC.issued);
  const leads = FC.seasons.length;
  const obs = OBS.map((o) => ({ m: idx(o.end), v: o.roni })).filter((o) => o.m > M - 24 && o.m <= M + leads);
  const x0 = obs.length ? obs[0].m : M - 24, x1 = M + leads;
  const showPast = opts.showPast;
  const past = showPast ? PAST.filter((p) => p.issued !== FC.issued) : [];
  const official = (OFFICIAL?.values ? Object.entries(OFFICIAL.values) : [])
    .map(([s, v]) => ({ i: FC.seasons.indexOf(s), v })).filter((o) => o.i >= 0);

  const vals = [...obs.map((o) => o.v), ...FC.ensemble.map((v, i) => v + Z80 * FC.sigma[i]),
    ...FC.ensemble.map((v, i) => v - Z80 * FC.sigma[i]), ...Object.values(FC.models).flat(), ...official.map((o) => o.v)];
  const lo = Math.min(-1.5, Math.floor((Math.min(...vals) - 0.2) * 2) / 2);
  const hi = Math.max(1.5, Math.ceil((Math.max(...vals) + 0.2) * 2) / 2);

  const f = frame(opts.sel, 400);
  const X = (m) => f.m.l + ((m - x0) / (x1 - x0)) * f.iw;
  const Y = (v) => f.m.t + ((hi - v) / (hi - lo)) * f.ih;
  const g = el("g", {}, f.svg);

  // grid and axes
  const grid = el("g", { class: "grid" }, g);
  for (let v = lo; v <= hi + 1e-9; v += 0.5) {
    el("line", { x1: f.m.l, x2: f.W - f.m.r, y1: Y(v), y2: Y(v) }, grid);
    text(g, f.m.l - 8, Y(v) + 4, sign(v, 1), { "text-anchor": "end" });
  }
  el("line", { class: "zero", x1: f.m.l, x2: f.W - f.m.r, y1: Y(0), y2: Y(0) }, g);
  for (const t of [0.5, -0.5]) el("line", { class: "thresh", x1: f.m.l, x2: f.W - f.m.r, y1: Y(t), y2: Y(t) }, g);
  text(g, f.W - f.m.r + 6, Y(0.5) - 4, "El Niño ↑");
  text(g, f.W - f.m.r + 6, Y(-0.5) + 13, "La Niña ↓");
  const step = f.iw < 420 ? 12 : f.iw < 620 ? 6 : 3;
  for (let m = x0; m <= x1; m++) {
    if (((m - 1) % 12 + 12) % 12 % step !== 0) continue;
    text(g, X(m), f.H - 12, seasonOf(m), { "text-anchor": "middle" });
  }
  // "today" divider
  el("line", { x1: X(M), x2: X(M), y1: f.m.t, y2: f.H - f.m.b, class: "cross", "stroke-dasharray": "2 3" }, g);
  text(g, X(M) + 4, f.m.t + 10, "forecast →");

  // 80% band
  const top = FC.ensemble.map((v, i) => [X(M + i + 1), Y(v + Z80 * FC.sigma[i])]);
  const bot = FC.ensemble.map((v, i) => [X(M + i + 1), Y(v - Z80 * FC.sigma[i])]).reverse();
  const start = [X(M), Y(FC.latest_observed.roni)];
  el("path", { d: linePath([start, ...top, ...bot, start]) + "Z", style: "fill:var(--band)" }, g);

  // earlier live forecasts
  for (const p of past) {
    const pm = idx(p.issued);
    el("path", { d: linePath(p.ensemble.map((v, i) => [X(pm + i + 1), Y(v)]).filter((q) => q[0] >= f.m.l)),
      style: "fill:none;stroke:var(--series-3);stroke-width:1.25;opacity:.75" }, g);
  }
  // individual models (context) and persistence
  for (const [name, arr] of Object.entries(FC.models)) {
    const pts = [start, ...arr.map((v, i) => [X(M + i + 1), Y(v)])];
    el("path", { d: linePath(pts), style: `fill:none;stroke:var(--text-muted);stroke-width:1.25;${name === "Persistence" ? "stroke-dasharray:5 4;" : "opacity:.7;"}` }, g);
  }
  // observed
  el("path", { d: linePath(obs.map((o) => [X(o.m), Y(o.v)])), style: "fill:none;stroke:var(--text-primary);stroke-width:2" }, g);
  // ensemble
  const ensPts = FC.ensemble.map((v, i) => [X(M + i + 1), Y(v)]);
  el("path", { d: linePath([start, ...ensPts]), style: "fill:none;stroke:var(--series-1);stroke-width:2" }, g);
  for (const [px, py] of ensPts) el("circle", { cx: px, cy: py, r: 4, style: "fill:var(--series-1);stroke:var(--surface-1);stroke-width:2" }, g);
  // official forecast dots
  for (const o of official) el("circle", { cx: X(M + o.i + 1), cy: Y(o.v), r: 4.5, style: "fill:var(--series-2);stroke:var(--surface-1);stroke-width:2" }, g);
  // direct label for the ensemble at its last point
  const last = ensPts[ensPts.length - 1];
  text(g, last[0] + 8, last[1] + 4, "Forecast", { style: "fill:var(--text-primary);font-weight:600" });

  // hover layer
  const cross = el("line", { class: "cross", y1: f.m.t, y2: f.H - f.m.b, visibility: "hidden" }, g);
  const hot = el("rect", { class: "hot", x: f.m.l, y: f.m.t, width: f.iw, height: f.ih, fill: "transparent" }, g);
  hot.addEventListener("mousemove", (e) => {
    const r = f.svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * f.W;
    const m = Math.round(x0 + ((px - f.m.l) / f.iw) * (x1 - x0));
    cross.setAttribute("x1", X(m)); cross.setAttribute("x2", X(m)); cross.setAttribute("visibility", "visible");
    let html = `<b>${seasonOf(m)}</b>`;
    const o = OBS.find((q) => idx(q.end) === m);
    if (o) html += row("Observed", sign(o.roni), "var(--text-primary)");
    const i = m - M - 1;
    if (i >= 0 && i < leads) {
      html += row("Forecast", sign(FC.ensemble[i]), "var(--series-1)");
      html += row("80% range", `${sign(FC.ensemble[i] - Z80 * FC.sigma[i], 1)} to ${sign(FC.ensemble[i] + Z80 * FC.sigma[i], 1)}`);
      for (const [name, arr] of Object.entries(FC.models)) html += row(name, sign(arr[i]), "var(--text-muted)", true);
      const off = official.find((q) => q.i === i);
      if (off) html += row(OFFICIAL.short || "Official", sign(off.v), "var(--series-2)");
      html += row("El Niño chance", pct(FC.probabilities[i].el_nino));
    }
    for (const p of past) {
      const j = m - idx(p.issued) - 1;
      if (j >= 0 && j < p.ensemble.length) html += row(`Made ${p.issued}`, sign(p.ensemble[j]), "var(--series-3)");
    }
    showTip(e, html);
  });
  hot.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); hideTip(); });

  const items = [["Observed", "var(--text-primary)"], ["Forecast (average of 3 models)", "var(--series-1)"],
    ["80% range", "var(--band)", "box"], ["Individual models", "var(--text-muted)"], ["Persistence (no change)", "var(--text-muted)", "dash"]];
  if (official.length) items.push([OFFICIAL.source || "Official forecast", "var(--series-2)", "dot"]);
  if (past.length) items.push(["My earlier forecasts", "var(--series-3)"]);
  legend(opts.legend, items);
}

/* ---------- probability bars ---------- */
function renderProbs() {
  const f = frame("#probs", 220, { t: 8, r: 8, b: 34, l: 44 });
  const n = FC.seasons.length, gap = 2;
  const bw = f.iw / n;
  const Y = (p) => f.m.t + (1 - p) * f.ih;
  const g = el("g", {}, f.svg);
  for (const p of [0, 0.5, 1]) {
    el("line", { x1: f.m.l, x2: f.W - f.m.r, y1: Y(p), y2: Y(p), style: "stroke:var(--grid)" }, g);
    text(g, f.m.l - 8, Y(p) + 4, pct(p), { "text-anchor": "end" });
  }
  const parts = [["la_nina", "La Niña", "var(--nina)"], ["neutral", "Neutral", "var(--neutral)"], ["el_nino", "El Niño", "var(--nino)"]];
  FC.probabilities.forEach((pr, i) => {
    const x = f.m.l + i * bw + gap / 2;
    let acc = 0;
    const col = el("g", {}, g);
    parts.forEach(([k, , color]) => {
      const h = pr[k] * f.ih;
      if (h > 0.5) el("rect", { x, y: Y(acc + pr[k]), width: bw - gap, height: Math.max(0, h - gap), rx: 3, style: `fill:${color}` }, col);
      acc += pr[k];
    });
    const [k] = parts.reduce((best, p) => (pr[p[0]] > pr[best[0]] ? p : best));
    if (pr[k] >= 0.5 && bw > 34) {
      let below = 0;
      for (const p of parts) { if (p[0] === k) break; below += pr[p[0]]; }
      text(col, x + (bw - gap) / 2, Y(below + pr[k] / 2) + 4, pct(pr[k]),
        { "text-anchor": "middle", style: `fill:${k === "neutral" ? "var(--text-primary)" : "#fff"};font-weight:600` });
    }
    if (bw > 30 || i % 2 === 0) text(g, x + (bw - gap) / 2, f.H - 12, bw > 60 ? FC.seasons[i] : FC.seasons[i].slice(0, 3), { "text-anchor": "middle" });
    const hot = el("rect", { x: x - gap / 2, y: f.m.t, width: bw, height: f.ih, fill: "transparent" }, col);
    hot.addEventListener("mousemove", (e) => showTip(e, `<b>${FC.seasons[i]}</b>` +
      parts.map(([kk, label, color]) => row(label, pct(pr[kk]), color)).reverse().join("")));
    hot.addEventListener("mouseleave", hideTip);
  });
  legend("#prob-legend", parts.map(([, l, c]) => [l, c, "box"]).reverse());
}

/* ---------- skill by lead ---------- */
const SKILL_SERIES = [["Ensemble", "var(--series-1)"], ["Neural net", "var(--series-2)"], ["Ridge", "var(--series-3)"],
  ["Analog", "var(--series-4)"], ["Persistence", "var(--series-5)"]];

function renderSkill() {
  if (!SKILL) return;
  $("#skill-note").textContent += ` Tested on ${SKILL.period}.`;
  const f = frame("#skill", 280, { t: 10, r: 12, b: 34, l: 40 });
  const leads = SKILL.by_model.Ensemble.length;
  const allC = SKILL_SERIES.flatMap(([n]) => SKILL.by_model[n].map((r) => r.corr));
  const lo = Math.min(0, Math.floor(Math.min(...allC) * 5) / 5);
  const X = (l) => f.m.l + ((l - 1) / (leads - 1)) * f.iw;
  const Y = (c) => f.m.t + ((1 - c) / (1 - lo)) * f.ih;
  const g = el("g", {}, f.svg);
  for (let c = lo; c <= 1.0001; c += 0.2) {
    el("line", { x1: f.m.l, x2: f.W - f.m.r, y1: Y(c), y2: Y(c), style: "stroke:var(--grid)" }, g);
    text(g, f.m.l - 6, Y(c) + 4, c.toFixed(1), { "text-anchor": "end" });
  }
  for (let l = 1; l <= leads; l += 2) text(g, X(l), f.H - 14, l, { "text-anchor": "middle" });
  text(g, f.m.l + f.iw / 2, f.H, "seasons ahead", { "text-anchor": "middle" });
  for (const [name, color] of [...SKILL_SERIES].reverse()) {
    const pts = SKILL.by_model[name].map((r) => [X(r.lead), Y(r.corr)]);
    el("path", { d: linePath(pts), style: `fill:none;stroke:${color};stroke-width:${name === "Ensemble" ? 2.5 : 2}` }, g);
  }
  const cross = el("line", { class: "cross", y1: f.m.t, y2: f.H - f.m.b, visibility: "hidden" }, g);
  const hot = el("rect", { x: f.m.l, y: f.m.t, width: f.iw, height: f.ih, fill: "transparent", class: "hot" }, g);
  hot.addEventListener("mousemove", (e) => {
    const r = f.svg.getBoundingClientRect();
    const l = Math.min(leads, Math.max(1, Math.round(1 + (((e.clientX - r.left) / r.width) * f.W - f.m.l) / f.iw * (leads - 1))));
    cross.setAttribute("x1", X(l)); cross.setAttribute("x2", X(l)); cross.setAttribute("visibility", "visible");
    showTip(e, `<b>${l} season${l > 1 ? "s" : ""} ahead</b>` + SKILL_SERIES.map(([n, c]) => {
      const s = SKILL.by_model[n][l - 1];
      return row(n, `${s.corr.toFixed(2)} <span style="color:var(--text-muted)">(±${s.rmse.toFixed(2)}°)</span>`, c);
    }).join(""));
  });
  hot.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); hideTip(); });
  legend("#skill-legend", SKILL_SERIES.map(([n, c]) => [n === "Persistence" ? "Persistence (no change)" : n, c]));
}

/* ---------- spring barrier heatmap ---------- */
const BINS = [[0.85, "--seq-5"], [0.7, "--seq-4"], [0.6, "--seq-3"], [0.5, "--seq-2"], [0.3, "--seq-1"], [-9, "--seq-0"]];
function renderBarrier() {
  if (!SKILL) return;
  const grid = SKILL.barrier;
  const leads = grid[0].length;
  const f = frame("#barrier", 330, { t: 6, r: 6, b: 54, l: 40 });
  const cw = f.iw / leads, ch = f.ih / 12, g = el("g", {}, f.svg);
  grid.forEach((r, mi) => {
    text(g, f.m.l - 6, f.m.t + mi * ch + ch / 2 + 4, MONTHS[mi], { "text-anchor": "end" });
    r.forEach((c, li) => {
      const color = c == null ? "--grid" : BINS.find(([t]) => c >= t)[1];
      const cell = el("rect", { x: f.m.l + li * cw + 1, y: f.m.t + mi * ch + 1, width: cw - 2, height: ch - 2, rx: 3, style: `fill:var(${color})` }, g);
      cell.addEventListener("mousemove", (e) => showTip(e, `<b>Made in ${MONTHS[mi]}, ${li + 1} season${li ? "s" : ""} ahead</b>${row("Correlation", c == null ? "–" : c.toFixed(2))}`));
      cell.addEventListener("mouseleave", hideTip);
    });
  });
  for (let l = 1; l <= leads; l += 2) text(g, f.m.l + (l - 0.5) * cw, f.m.t + f.ih + 14, l, { "text-anchor": "middle" });
  text(g, f.m.l + f.iw / 2, f.m.t + f.ih + 28, "seasons ahead", { "text-anchor": "middle" });
  // colour key
  const labels = ["<0.3", "0.3", "0.5", "0.6", "0.7", "0.85+"];
  const keyW = Math.min(46, f.iw / 6);
  [...BINS].reverse().forEach(([, c], i) => {
    const kx = f.m.l + i * keyW;
    el("rect", { x: kx + 1, y: f.H - 14, width: keyW - 2, height: 8, rx: 2, style: `fill:var(${c})` }, g);
    text(g, kx + keyW / 2, f.H - 18, labels[i], { "text-anchor": "middle", style: "font-size:10px" });
  });
}

/* ---------- tables ---------- */
function renderTrack() {
  const rows = (SCORE?.rows || []).slice().reverse();
  const s = SCORE?.summary;
  if (s) $("#track-note").textContent += ` So far: ${s.n} verified season${s.n > 1 ? "s" : ""}, average error ${s.mae.toFixed(2)}°C versus ${s.mae_persistence.toFixed(2)}°C for "no change".`;
  $("#track tbody").innerHTML = rows.length ? rows.slice(0, 60).map((r) => `<tr>
    <td>${esc(r.issued)}</td><td>${esc(r.season)}</td><td class="num">${r.lead}</td>
    <td class="num">${sign(r.forecast)}</td><td class="num">${sign(r.persistence)}</td>
    <td class="num"><b>${sign(r.observed)}</b></td><td class="num">${sign(r.forecast - r.observed)}</td></tr>`).join("")
    : `<tr><td colspan="7" class="empty">No forecast has come due yet. Check back next month: the first scores arrive as soon as NOAA publishes the next season.</td></tr>`;
}

function renderDetail() {
  const names = Object.keys(FC.models);
  const head = `<thead><tr><th>Season</th><th class="num">Forecast</th><th class="num">80% range</th><th>Most likely</th>
    <th class="num">La Niña</th><th class="num">Neutral</th><th class="num">El Niño</th>${names.map((n) => `<th class="num">${esc(n)}</th>`).join("")}</tr></thead>`;
  const body = FC.seasons.map((s, i) => `<tr><td>${esc(s)}</td><td class="num"><b>${sign(FC.ensemble[i])}</b></td>
    <td class="num">${sign(FC.ensemble[i] - Z80 * FC.sigma[i], 1)} to ${sign(FC.ensemble[i] + Z80 * FC.sigma[i], 1)}</td>
    <td>${esc(FC.category[i])}</td><td class="num">${pct(FC.probabilities[i].la_nina)}</td><td class="num">${pct(FC.probabilities[i].neutral)}</td>
    <td class="num">${pct(FC.probabilities[i].el_nino)}</td>${names.map((n) => `<td class="num">${sign(FC.models[n][i])}</td>`).join("")}</tr>`).join("");
  $("#detail").innerHTML = head + `<tbody>${body}</tbody>`;
}

/* ---------- replays ---------- */
async function renderReplay(label) {
  const R = await getJSON(`data/replays/${label}.json`, null);
  if (!R) return;
  plume({ sel: "#replay-chart", legend: "#replay-legend", fc: R, official: null, showPast: false });
  const n = R.observed.filter((o) => o != null).length;
  const inRange = R.observed.filter((o, i) => o != null && Math.abs(o - R.ensemble[i]) <= Z80 * R.sigma[i]).length;
  const phaseOk = R.observed.filter((o, i) => o != null && strength(o).split(" ").pop() === R.category[i].split(" ").pop()).length;
  const s = R.summary;
  $("#replay-tiles").innerHTML = !n ? `<p class="note">Nothing to compare yet: no later data.</p>` : [
    ["Average error", s.mae.toFixed(2) + "°C", `"No change" would have been off by ${s.mae_persistence.toFixed(2)}°C`],
    ["Right phase", `${phaseOk} of ${n}`, "seasons called correctly as El Niño, La Niña or neutral"],
    ["Inside the 80% range", `${inRange} of ${n}`, "about 80% is what a well-calibrated forecast should get"],
    ["Worst miss", s.max_error.toFixed(2) + "°C", `data through ${R.data_through}`],
  ].map(([l, v, f]) => `<div class="tile"><div class="label">${esc(l)}</div><div class="value">${esc(v)}</div><div class="tfoot">${esc(f)}</div></div>`).join("");
  $("#replay-table").innerHTML = `<thead><tr><th>Season</th><th class="num">Lead</th><th class="num">Forecast</th><th class="num">80% range</th>
    <th class="num">Persistence</th><th class="num">Observed</th><th class="num">Error</th></tr></thead><tbody>` +
    R.seasons.map((ss, i) => {
      const o = R.observed[i];
      return `<tr><td>${esc(ss)}</td><td class="num">${i + 1}</td><td class="num">${sign(R.ensemble[i])}</td>
        <td class="num">${sign(R.ensemble[i] - Z80 * R.sigma[i], 1)} to ${sign(R.ensemble[i] + Z80 * R.sigma[i], 1)}</td>
        <td class="num">${sign(R.models.Persistence[i])}</td><td class="num"><b>${o == null ? "not yet" : sign(o)}</b></td>
        <td class="num">${o == null ? "" : sign(R.ensemble[i] - o)}</td></tr>`;
    }).join("") + "</tbody>";
}

async function setupReplays() {
  const list = await getJSON("data/replays/index.json", []);
  if (!list.length) return;
  $("#replay-block").hidden = false;
  const pick = $("#replay-pick");
  pick.innerHTML = list.slice().reverse().map((m) => {
    const [y, mo] = m.split("-").map(Number);
    return `<option value="${esc(m)}">${MONTHS[mo - 1]} ${y}</option>`;
  }).join("");
  pick.addEventListener("change", () => renderReplay(pick.value));
  addEventListener("resize", () => { clearTimeout(pick._t); pick._t = setTimeout(() => renderReplay(pick.value), 150); });
  renderReplay(pick.value);
}

/* ---------- boot ---------- */
function renderCharts() { renderPlume(); renderProbs(); renderSkill(); renderBarrier(); }

async function boot() {
  [FC, OBS, SKILL, SCORE, OFFICIAL] = await Promise.all([
    getJSON("data/latest.json", null), getJSON("data/observed.json", []), getJSON("data/skill.json", null),
    getJSON("data/scorecard.json", null), getJSON("data/official.json", null)]);
  if (!FC) {
    $("#headline").textContent = "Waiting for the first forecast";
    $("#subline").textContent = "The GitHub Action hasn't run yet. Trigger it from the Actions tab.";
    document.querySelectorAll(".block, .tiles").forEach((b) => (b.hidden = true));
    return;
  }
  const list = await getJSON("data/index.json", []);
  PAST = (await Promise.all(list.slice(-12).map((m) => getJSON(`data/forecasts/${m}.json`, null)))).filter(Boolean);
  renderHeader();
  renderCharts();
  renderTrack();
  renderDetail();
  setupReplays();
  $("#show-past").addEventListener("change", renderPlume);
  let t;
  addEventListener("resize", () => { clearTimeout(t); t = setTimeout(renderCharts, 150); });
}
boot();
