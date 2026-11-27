// NOEMA-ORIN Always-On Mission Control UI (D4/#184)
// Strictly DOM-constructed via createElement/textContent per VISUAL-DESIGN.md.

const SVG_NS = "http://www.w3.org/2000/svg";
const ROLE_COLORS = {
  founder: "#C4A882",
  quartermaster: "#C6FF3D",
  custodian: "#3DDCFF",
  archivist: "#9B6DFF",
  speaker: "#FFB020",
  surveyor: "#7BF1A8",
};

const KIOSK = new URLSearchParams(window.location.search).get("kiosk") === "1";
const FEED_CAP = 200;
const FEED_SHOW = 40;

const state = {
  snapshot: null,
  turns: [],
  filter: "all",
  rolesOnly: KIOSK,
  selectedMember: null,
  token: localStorage.getItem("noema_dash_token") || "",
  lastEventTs: Date.now(),
  es: null,
  retryMs: 1500,
  map: null,
  mapSig: null,
  mapDrawnKey: null,
  cards: new Map(),
  feedDirty: false,
};
if (KIOSK) document.documentElement.classList.add("kiosk");

function el(tag, attrs = {}, text = null) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "style") node.setAttribute("style", v);
    else if (k.startsWith("data-")) node.setAttribute(k, String(v));
    else node[k] = v;
  }
  if (text !== null && text !== undefined) node.textContent = String(text);
  return node;
}

function svgEl(tag, attrs = {}, text = null) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (text !== null && text !== undefined) node.textContent = String(text);
  return node;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function toast(msg) {
  const box = document.getElementById("toast");
  box.textContent = msg;
  box.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => box.classList.add("hidden"), 3200);
}

function authHeaders(extra = {}) {
  const h = { ...extra };
  if (state.token) h["Authorization"] = "Bearer " + state.token;
  return h;
}

async function apiGet(path) {
  const res = await fetch(path, { headers: authHeaders() });
  if (res.status === 401) throw new Error("Unauthorized (click AUTH to set token)");
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body || {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "HTTP " + res.status);
  return data;
}

function showModal({ title, msg, danger = true, input = false, onConfirm }) {
  const bd = document.getElementById("modal-backdrop");
  const mTitle = document.getElementById("modal-title");
  const mMsg = document.getElementById("modal-msg");
  const mIn = document.getElementById("modal-input");
  const mOk = document.getElementById("modal-confirm");
  const mCancel = document.getElementById("modal-cancel");

  mTitle.textContent = title;
  mMsg.textContent = msg;
  mIn.value = input ? state.token : "";
  mIn.classList.toggle("hidden", !input);
  mOk.className = danger ? "btn btn-danger" : "btn btn-cyan";
  bd.classList.remove("hidden");

  const close = () => bd.classList.add("hidden");
  mCancel.onclick = close;
  mOk.onclick = async () => {
    const val = mIn.value;
    close();
    await onConfirm(val);
  };
}

function fmtVal(v, suffix = "") {
  if (v === null || v === undefined || v === "NOT_COMPUTABLE") return "N/C";
  return String(v) + suffix;
}

function renderTopbar(snap) {
  const orgRaw = snap.home_org || "";
  const orgName = orgRaw.startsWith("org.")
    ? orgRaw.slice(4).replace(/\.[0-9a-f]{6,}$/, "").split("-").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")
    : (orgRaw || "Reach Compact");
  const orgEl = document.getElementById("org-label");
  orgEl.textContent = orgName + " · Perihelion Reach";
  orgEl.title = orgRaw;
  document.getElementById("seq-pill").textContent = "SEQ " + (snap.world_seq || "—");

  const activeAgents = (snap.agents || []).filter((a) => a.unit_state === "active").length;
  const fleetPill = document.getElementById("fleet-pill");
  fleetPill.textContent = `UNITS ${activeAgents}/${(snap.agents || []).length}`;
  fleetPill.className = activeAgents === (snap.agents || []).length ? "pill pill-active" : "pill pill-warn";

  const hw = snap.hw || {};
  document.getElementById("hw-gpu").textContent = fmtVal(hw.gpu_load_pct, "%");
  document.getElementById("hw-temp").textContent = hw.gpu_temp_c && hw.gpu_temp_c !== "NOT_COMPUTABLE"
    ? `${hw.cpu_temp_c}/${hw.gpu_temp_c}°C`
    : fmtVal(hw.cpu_temp_c, "°C");
  document.getElementById("hw-pwr").textContent = typeof hw.vdd_in_mw === "number" ? (hw.vdd_in_mw / 1000).toFixed(1) + "W" : "N/C";
  const memMib = typeof hw.mem_avail_mib === "number" ? hw.mem_avail_mib : null;
  document.getElementById("hw-ram").textContent = memMib !== null ? (memMib / 1024).toFixed(1) + "G" : "N/C";
  const ramBar = document.getElementById("hw-ram-bar");
  const ramChip = document.getElementById("chip-ram");
  if (memMib !== null) {
    // Bar scale: 0..3 GiB available. Warn under 1 GiB, critical under 512 MiB.
    ramBar.style.width = Math.max(3, Math.min(100, (memMib / 3072) * 100)) + "%";
    ramChip.classList.toggle("warn", memMib < 1024 && memMib >= 512);
    ramChip.classList.toggle("crit", memMib < 512);
  }
  const tpsIdle = hw.llama_tps === 0 || hw.llama_tps === "0";
  document.getElementById("hw-tps").textContent = tpsIdle ? "idle" : fmtVal(hw.llama_tps, " t/s");
  document.getElementById("hw-s1rate").textContent = typeof hw.llama_req_per_min === "number" ? String(hw.llama_req_per_min) : "…";
  document.getElementById("hw-embrate").textContent = typeof hw.embed_per_min === "number" ? String(hw.embed_per_min) : "…";

  const toks = snap.tokens || [];
  const minDays = toks.reduce((acc, r) => (typeof r.days_left === "number" ? Math.min(acc, r.days_left) : acc), Infinity);
  const tokEl = document.getElementById("tok-min");
  tokEl.textContent = minDays === Infinity ? "N/C" : `${minDays}d`;
  tokEl.style.color = minDays <= 3 ? "var(--crit)" : minDays <= 7 ? "var(--warn)" : "var(--eco)";

  const inf = snap.inference_totals || {};
  const tot = Math.max(1, (inf.planner || 0) + (inf.local_s1 || 0) + (inf.workers_ai || 0) + (inf.idle_skip || 0) + (inf.fallback || 0));
  const pPct = Math.round(((inf.planner || 0) * 100) / tot);
  const s1Pct = Math.round(((inf.local_s1 || 0) * 100) / tot);
  const s2Pct = Math.round(((inf.workers_ai || 0) * 100) / tot);
  const iPct = Math.max(0, 100 - pPct - s1Pct - s2Pct);
  const bar = document.getElementById("inference-bar");
  bar.children[0].style.width = pPct + "%";
  bar.children[1].style.width = s1Pct + "%";
  bar.children[2].style.width = s2Pct + "%";
  bar.children[3].style.width = iPct + "%";
  document.getElementById("inference-legend").textContent = `P ${pPct}% · S1 ${s1Pct}% · S2 ${s2Pct}%`;

  const ov = snap.runtime_overrides || {};
  const nLocal = (snap.agents || []).filter((a) => a.inference_mode === "local_first").length;
  const nAll = (snap.agents || []).length;
  const modeTxt = nLocal === 0 ? "cloud_first" : nLocal === nAll ? "local_first" : `local_first ${nLocal}/${nAll}`;
  document.getElementById("mode-pill").textContent = `MODE: ${modeTxt} · VOICE: ${ov.NOEMA_GROUNDED_VOICE === "1" ? "ON" : "OFF"}`;
  document.getElementById("sel-inf-mode").value = ov.NOEMA_INFERENCE_MODE || "cloud_first";
  document.getElementById("chk-voice").checked = ov.NOEMA_GROUNDED_VOICE === "1";

  const banner = document.getElementById("alert-banner");
  const muted = document.getElementById("alert-muted");
  const items = snap.alert_items || (snap.alerts || []).map((t) => ({ level: "warn", text: t }));
  const loud = items.filter((a) => a.level !== "expected");
  const quiet = items.filter((a) => a.level === "expected");
  if (loud.length) {
    banner.textContent = "ALERTS (" + loud.length + "): " + loud.slice(0, 4).map((a) => a.text).join("  |  ");
    banner.classList.remove("hidden");
    banner.classList.toggle("crit", loud.some((a) => a.level === "crit"));
  } else {
    banner.classList.add("hidden");
  }
  if (quiet.length && !KIOSK) {
    muted.textContent = "expected: " + quiet.map((a) => a.text).join(" · ");
    muted.classList.remove("hidden");
  } else {
    muted.classList.add("hidden");
  }
}

function makeMeter(label) {
  const wrap = el("div", { class: "b-meter" });
  const head = el("div", { class: "b-head" });
  const val = el("span", {}, "—");
  head.append(el("span", {}, label), val);
  const track = el("div", { class: "b-track" });
  const fill = el("div", { class: "b-fill" });
  track.append(fill);
  wrap.append(head, track);
  return { wrap, val, fill };
}

function setMeter(m, value, maxVal, tone = "") {
  const txt = value === undefined || value === null ? "—" : String(value);
  if (m.val.textContent !== txt) m.val.textContent = txt;
  const pct = typeof value === "number" ? Math.max(0, Math.min(100, (value / maxVal) * 100)) : 0;
  m.fill.style.width = pct + "%";
  const cls = "b-fill" + (tone ? " " + tone : "");
  if (m.fill.className !== cls) m.fill.className = cls;
}

function setText(node, txt) {
  const s = txt === null || txt === undefined ? "" : String(txt);
  if (node.textContent !== s) node.textContent = s;
}

function sparkPath(spark, w, h) {
  // Rolling share of role turns over a 10-turn window, plotted across the last 50 turns.
  if (!spark || spark.length < 2) return "";
  const win = 10;
  const pts = [];
  for (let i = 0; i < spark.length; i++) {
    const lo = Math.max(0, i - win + 1);
    let s = 0;
    for (let j = lo; j <= i; j++) s += spark[j];
    const v = s / (i - lo + 1);
    pts.push([(i / (spark.length - 1)) * w, h - v * (h - 2) - 1]);
  }
  return "M" + pts.map((p) => p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" L");
}

function buildCard(a) {
  const card = el("article", { class: "agent-card", "data-member": a.member });
  card.onclick = () => openDrawer(a.member);
  const top = el("div", { class: "card-top" });
  const idCol = el("div");
  const handle = el("div", { class: "card-handle" });
  const roleLine = el("div", { class: "card-role" });
  idCol.append(handle, roleLine);
  const badges = el("div", { class: "card-badges" });
  top.append(idCol, badges);

  const health = el("div", { class: "card-health" });
  const pct = el("div", { class: "role-pct" });
  const pctLbl = el("div", { class: "role-pct-lbl" }, "ROLE · LAST 50");
  const pctCol = el("div", { class: "role-pct-col" });
  pctCol.append(pct, pctLbl);
  const svg = svgEl("svg", { class: "spark", viewBox: "0 0 120 28", preserveAspectRatio: "none" });
  const sparkLine = svgEl("path", { d: "", fill: "none", "stroke-width": 1.6 });
  svg.append(sparkLine);
  const since = el("div", { class: "role-since" });
  health.append(pctCol, svg, since);

  const room = el("div", { class: "card-room" });
  const roomName = el("span");
  const rates = el("span");
  room.append(roomName, rates);
  const actLine = el("div", { class: "card-action" });
  // C4 (#199): shadow-mode accuracy of the consequence model. Read-only, hidden when the member has none.
  const shadow = el("div", { class: "card-action card-shadow", title: "Consequence model, shadow mode, last 24h. INFERRED estimates; they do not change what the agent does." });
  shadow.hidden = true;

  const budgets = el("div", { class: "budgets-row" });
  const meters = { eng: makeMeter("ENG"), att: makeMeter("ATT"), cmp: makeMeter("CMP"), crg: makeMeter("CRG") };
  budgets.append(meters.eng.wrap, meters.att.wrap, meters.cmp.wrap, meters.crg.wrap);

  const foot = el("div", { class: "card-foot" });
  const tracks = el("div", { class: "tracks-row" });
  const rstBtn = el("button", { type: "button", class: "btn btn-xs ctl" }, "RESTART");
  rstBtn.onclick = (ev) => {
    ev.stopPropagation();
    controlUnit(a.unit, "restart");
  };
  foot.append(tracks, rstBtn);
  card.append(top, health, room, actLine, shadow, budgets, foot);
  return { card, handle, roleLine, badges, pct, sparkLine, since, roomName, rates, actLine, shadow, meters, tracks, badgeKey: "", trackKey: "" };
}

function updateCard(c, a, pulsed) {
  const b = a.budgets || {};
  const lowE = typeof b.energy === "number" && b.energy <= 1;
  const isDown = a.unit_state !== "active" && a.unit_state !== "unknown";
  const cls = "agent-card" + (pulsed ? " pulse" : "") + (isDown || lowE ? " state-crit" : a.rsi_status.startsWith("CANARY") ? " state-warn" : "");
  if (c.card.className !== cls) c.card.className = cls;
  setText(c.handle, a.handle);
  setText(c.roleLine, `${a.member} · ${a.role} · v${a.persona_version}`);

  const badgeKey = [a.unit_state, a.rsi_status, a.inference_mode, a.semantic_memory].join("|");
  if (badgeKey !== c.badgeKey) {
    c.badgeKey = badgeKey;
    clear(c.badges);
    c.badges.append(
      el("span", { class: a.unit_state === "active" ? "pill pill-active" : "pill pill-warn" }, a.unit_state.toUpperCase()),
      el("span", { class: a.rsi_status.startsWith("CANARY") ? "pill pill-warn" : "pill pill-violet" }, a.rsi_status),
    );
    if (a.inference_mode === "local_first") c.badges.append(el("span", { class: "pill pill-eco", title: "System-1 on local llama-server" }, "LOCAL"));
    if (a.semantic_memory) c.badges.append(el("span", { class: "pill pill-eco", title: "bge-small semantic recall" }, "EMB"));
  }

  const rr = typeof a.role_rate_recent === "number" ? a.role_rate_recent : 0;
  setText(c.pct, Math.round(rr * 100) + "%");
  const tone = rr >= 0.3 ? "good" : rr >= 0.1 ? "mid" : "low";
  const pctCls = "role-pct " + tone;
  if (c.pct.className !== pctCls) c.pct.className = pctCls;
  c.sparkLine.setAttribute("d", sparkPath(a.role_spark, 120, 28));
  c.sparkLine.setAttribute("stroke", ROLE_COLORS[a.role] || "#3DDCFF");
  const n = a.turns_since_role;
  setText(c.since, n === null || n === undefined ? "no role action in window" : n === 0 ? `${a.last_role_action} · now` : `${a.last_role_action} · ${n} turns ago`);

  setText(c.roomName, (a.room_id || "unknown").replace(/^room\./, ""));
  setText(c.rates, `24h ROLE ${Math.round((a.role_action_rate || 0) * 100)}% · STALE ${Math.round((a.stale_head_rate || 0) * 100)}%`);
  const stepTxt = a.active_step ? ` · goal:${a.active_step.goal_kind}` : "";
  setText(c.actLine, `${a.last_action || "—"} ${a.last_target || ""} [${a.last_source || "—"}]${stepTxt}`);
  const cq = a.consequence;
  const hasShadow = !!cq && typeof cq === "object";
  if (c.shadow.hidden === hasShadow) c.shadow.hidden = !hasShadow;
  if (hasShadow) {
    const share = (v) => (typeof v === "number" ? Math.round(v * 100) + "%" : "N/C");
    setText(c.shadow, `SHADOW INFERRED · ${cq.predictions || 0} pred · reject P ${share(cq.rejection_precision)} R ${share(cq.rejection_recall)} · none ${share(cq.no_prediction_share)}`);
  }

  const cargoUsed = typeof b.storage === "number" ? 16 - b.storage : null;
  setMeter(c.meters.eng, b.energy, 16, lowE ? "low" : "");
  setMeter(c.meters.att, b.attention, 8, typeof b.attention === "number" && b.attention < 2 ? "warn" : "");
  setMeter(c.meters.cmp, b.compute, 64, "");
  setMeter(c.meters.crg, cargoUsed, 16, "eco");

  const trackKey = (a.held_tracks || []).join(",") + "|" + a.min_tool_condition;
  if (trackKey !== c.trackKey) {
    c.trackKey = trackKey;
    clear(c.tracks);
    for (const tr of a.held_tracks || []) c.tracks.append(el("span", { class: "track-tag" }, tr));
    if (a.min_tool_condition !== null && a.min_tool_condition !== undefined) {
      c.tracks.append(el("span", { class: "track-tag" }, `tool ${a.min_tool_condition}%`));
    }
  }
}

function renderAgents(snap, pulsedMember = null) {
  const grid = document.getElementById("agent-grid");
  const seen = new Set();
  for (const a of snap.agents || []) {
    seen.add(a.member);
    let c = state.cards.get(a.member);
    if (!c) {
      c = buildCard(a);
      state.cards.set(a.member, c);
      grid.append(c.card);
    }
    updateCard(c, a, pulsedMember === a.member);
  }
  for (const [m, c] of state.cards) {
    if (!seen.has(m)) {
      c.card.remove();
      state.cards.delete(m);
    }
  }

  const infra = document.getElementById("infra-units");
  const infraKey = ["noema-maint-patrol", "noema-llama-server", "noema-embed-server"].map((u) => ((snap.units || {})[u] || {}).active_state).join("|");
  if (infra.dataset.key === infraKey) return;
  infra.dataset.key = infraKey;
  clear(infra);
  for (const uname of ["noema-maint-patrol", "noema-llama-server", "noema-embed-server"]) {
    const st = (snap.units || {})[uname] || { active_state: "unknown" };
    const pill = el("button", {
      type: "button",
      class: st.active_state === "active" ? "pill pill-active" : "pill pill-warn",
      title: `Click to restart ${uname}`,
    }, `${uname.replace("noema-", "")}: ${st.active_state}`);
    pill.onclick = () => controlUnit(uname, "restart");
    infra.append(pill);
  }
}

function renderReachMap(snap) {
  const m = state.map || {};
  const posKey = (snap.agents || []).map((a) => `${a.member}@${a.room_id}`).join(",");
  const key = `${state.mapSig}|${posKey}`;
  if (key === state.mapDrawnKey) return; // nothing moved: keep the existing SVG
  state.mapDrawnKey = key;

  const svg = document.getElementById("reach-svg");
  clear(svg);
  const rooms = m.rooms || [];
  const W = 640, H = 270, CX = W / 2, CY = H / 2;
  const LABEL = KIOSK ? 12 : 10.5;

  for (const r of [56, 106, 156]) {
    svg.append(svgEl("circle", { cx: CX, cy: CY, r, fill: "none", stroke: "#1C232B", "stroke-width": 1, "stroke-dasharray": "3 5" }));
  }
  if (!rooms.length) {
    svg.append(svgEl("text", { x: CX, y: CY, fill: "#A8A39A", "text-anchor": "middle", "font-family": "IBM Plex Mono", "font-size": 12 }, "No rooms observed in shared/map.db yet."));
    return;
  }

  const coords = {};
  const hub = rooms.find((r) => r.room_id === "room.civic-exchange") || rooms[0];
  coords[hub.room_id] = { x: CX, y: CY };
  const others = rooms.filter((r) => r.room_id !== hub.room_id);
  others.forEach((r, idx) => {
    const angle = (idx / Math.max(1, others.length)) * Math.PI * 2 - Math.PI / 2;
    const rx = others.length > 6 && idx % 2 === 1 ? 235 : 175;
    const ry = others.length > 6 && idx % 2 === 1 ? 105 : 88;
    coords[r.room_id] = { x: CX + Math.cos(angle) * rx, y: CY + Math.sin(angle) * ry };
  });

  const drawn = new Set();
  for (const ex of m.exits || []) {
    const a = coords[ex.room_id], b = coords[ex.dest];
    if (!a || !b) continue;
    const k = [ex.room_id, ex.dest].sort().join("|");
    if (drawn.has(k)) continue;
    drawn.add(k);
    svg.append(svgEl("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: "#2A333C", "stroke-width": 1.5 }));
  }

  const scarRooms = new Set((m.scars || []).map((s) => s.room_id));
  const stallRooms = new Set((m.stalls || []).map((s) => s.room_id));
  const workRooms = new Set((m.shared_work || []).map((w) => w.room_id));

  for (const r of rooms) {
    const c = coords[r.room_id];
    const pres = ((m.pressure || {})[r.room_id] || {}).harvest_pressure || 0;
    const hasWork = workRooms.has(r.room_id);
    if (scarRooms.has(r.room_id) || pres >= 2 || hasWork) {
      // Pulsing halo: open work (amber) or scar/pressure (violet) needs attention.
      const col = hasWork ? "#FFB020" : "#9B6DFF";
      svg.append(svgEl("circle", { class: "halo", cx: c.x, cy: c.y, r: 22, fill: "none", stroke: col, "stroke-width": 1.4 }));
    }
    const stroke = stallRooms.has(r.room_id) ? "#C6FF3D" : hasWork ? "#FFB020" : "#3DDCFF";
    svg.append(svgEl("circle", { cx: c.x, cy: c.y, r: r.room_id === hub.room_id ? 14 : 10, fill: "#161B20", stroke, "stroke-width": 1.8 }));
    const label = (r.name || r.room_id.replace(/^room\./, "")).slice(0, 18);
    // Hub label goes above the node so the agent fan below it stays readable.
    const ly = r.room_id === hub.room_id ? c.y - 20 : c.y + 26;
    svg.append(svgEl("text", { x: c.x, y: ly, fill: "#E8E4DC", "text-anchor": "middle", "font-family": "IBM Plex Mono", "font-size": LABEL, "paint-order": "stroke", stroke: "#0E1114", "stroke-width": 3 }, label));
  }

  const byRoom = {};
  for (const a of snap.agents || []) {
    if (!a.room_id || !coords[a.room_id]) continue;
    (byRoom[a.room_id] ||= []).push(a);
  }
  for (const [rid, list] of Object.entries(byRoom)) {
    const c = coords[rid];
    const many = list.length > 2;
    // Several agents in one room: fan them onto a wider lower arc with leader lines, instead of a pile.
    const radius = many ? 40 : 19;
    list.forEach((a, i) => {
      const span = many ? Math.PI * 0.9 : Math.PI * 2;
      const start = many ? Math.PI * 0.05 : -Math.PI / 4;
      const ang = start + (list.length === 1 ? 0 : (i / (many ? list.length - 1 : list.length)) * span);
      const px = c.x + Math.cos(ang) * radius * (many ? 1.6 : 1);
      const py = c.y + Math.sin(ang) * radius;
      const col = ROLE_COLORS[a.role] || "#3DDCFF";
      if (many) svg.append(svgEl("line", { x1: c.x, y1: c.y, x2: px, y2: py, stroke: col, "stroke-opacity": 0.35, "stroke-width": 1 }));
      svg.append(svgEl("circle", { cx: px, cy: py, r: KIOSK ? 6.5 : 5.5, fill: col, stroke: "#0E1114", "stroke-width": 1.2 }));
      svg.append(svgEl("text", { x: px, y: py + (many ? 15 : -8), fill: col, "text-anchor": "middle", "font-family": "IBM Plex Mono", "font-size": KIOSK ? 11 : 9.5, "font-weight": 700, "paint-order": "stroke", stroke: "#0E1114", "stroke-width": 3 }, a.member));
    });
  }
}

function feedRows() {
  // Visible rows after filters, with consecutive identical turns collapsed to "xN".
  const out = [];
  for (const t of state.turns) {
    if (state.filter !== "all" && t.member !== state.filter) continue;
    if (state.rolesOnly && t.is_role === false) continue;
    const sig = `${t.member}|${t.action}|${t.target || ""}|${t.source || ""}`;
    const prev = out[out.length - 1];
    if (prev && prev.sig === sig) {
      prev.count += 1;
      continue;
    }
    out.push({ t, sig, count: 1 });
    if (out.length >= FEED_SHOW) break;
  }
  return out;
}

function renderFeed() {
  const box = document.getElementById("turn-feed");
  const rows = feedRows();
  clear(box);
  if (!rows.length) {
    box.append(el("div", { class: "list-item" }, state.rolesOnly ? "Awaiting role actions..." : "Awaiting live turns..."));
    return;
  }
  for (const { t, count } of rows) {
    const src = t.source || "planner";
    const row = el("div", { class: `feed-row src-${src}` + (t.is_role ? " is-role" : "") });
    const eng = (t.budgets || {}).energy;
    row.append(
      el("span", { style: `color:${ROLE_COLORS[t.role] || "#3DDCFF"}` }, t.member || "?"),
      el("span", {}, String(t.room || "").replace(/^room\./, "").slice(0, 15)),
      el("span", { style: "color:var(--ink-2)" }, src),
      el("span", {}, `${t.action || "?"} ${t.target || ""}`.trim() + (count > 1 ? `  ×${count}` : "")),
      el("span", { style: eng <= 1 ? "color:var(--crit)" : "color:var(--machine)" }, eng !== undefined ? `E:${eng}` : ""),
    );
    box.append(row);
  }
}

function scheduleFeed() {
  // Turn bursts (6 agents) coalesce into one feed render per animation frame.
  if (state.feedDirty) return;
  state.feedDirty = true;
  requestAnimationFrame(() => {
    state.feedDirty = false;
    renderFeed();
  });
}

function renderEconomyAndAudit(snap) {
  const m = snap.map || {};
  const listBox = document.getElementById("listings-list");
  clear(listBox);
  if (!(m.listings || []).length) {
    listBox.append(el("div", { class: "list-item" }, "No open barter_stall listings observed."));
  } else {
    for (const l of m.listings.slice(0, 10)) {
      listBox.append(el("div", { class: "list-item" }, `${l.listing_kind} · fills ${l.fills_remaining} · seq ${l.seen_seq}`));
    }
  }

  const claimBox = document.getElementById("claims-list");
  clear(claimBox);
  if (!(m.claims || []).length) {
    claimBox.append(el("div", { class: "list-item" }, "No active cohort_claims."));
  } else {
    for (const c of m.claims) {
      const row = el("div", { class: "list-item" });
      row.append(el("span", {}, `${c.target_id} (${c.member} · ${c.action} exp:${c.expires_seq})`));
      const btn = el("button", { type: "button", class: "btn btn-xs" }, "RELEASE");
      btn.onclick = async () => {
        try {
          await apiPost("/api/control/claims/release", { target_id: c.target_id });
          toast(`Released claim ${c.target_id}`);
          await refreshSnapshot();
        } catch (err) { toast(err.message); }
      };
      row.append(btn);
      claimBox.append(row);
    }
  }

  const workBox = document.getElementById("work-list");
  clear(workBox);
  if (!(m.shared_work || []).length) {
    workBox.append(el("div", { class: "list-item" }, "No damaged infra in shared_work."));
  } else {
    for (const w of m.shared_work.slice(0, 8)) {
      workBox.append(el("div", { class: "list-item" }, `${w.action} ${w.target_id} @ ${w.room_id.replace(/^room\./, "")} (${w.condition}%)`));
    }
  }

  const auditBox = document.getElementById("audit-list");
  clear(auditBox);
  for (const a of (snap.audit || []).slice(0, 12)) {
    auditBox.append(el("div", { class: "list-item" }, `${a.ok ? "OK" : "ERR"} ${a.action} · ${JSON.stringify(a.detail || {}).slice(0, 72)}`));
  }
}

async function openDrawer(member, query = "") {
  state.selectedMember = member;
  const drawer = document.getElementById("drawer");
  drawer.classList.remove("hidden");
  try {
    const d = await apiGet(`/api/agent/${member}?q=${encodeURIComponent(query)}`);
    const p = d.persona || {};
    document.getElementById("drawer-title").textContent = `${p.name || member} · ${p.role || ""}`;
    document.getElementById("drawer-sub").textContent = `${member} · persona v${p.version || 0} (${(d.persona_versions || []).length} snapshots) · ${d.embedding_count || 0} TRT embeddings`;

    const pBox = document.getElementById("drawer-persona");
    clear(pBox);
    pBox.append(
      el("div", {}, `Voice: ${p.voice || "—"}`),
      el("div", {}, `Quirk: ${p.quirk || "—"}`),
      el("div", { style: "margin-bottom:6px;color:var(--ink-2)" }, `Value: ${p.value || "—"}`),
    );
    for (const [k, v] of Object.entries(p.traits || {})) {
      const r = el("div", { class: "trait-row" });
      r.append(el("span", {}, k));
      const tr = el("div", { class: "b-track" });
      tr.append(el("div", { class: "b-fill", style: `width:${Math.round(Number(v) * 100)}%` }));
      r.append(tr, el("span", {}, String(v)));
      pBox.append(r);
    }

    const aBox = document.getElementById("drawer-agenda");
    clear(aBox);
    const rs = d.rsi_state || {};
    aBox.append(el("div", { style: "margin-bottom:4px" }, `Baseline fitness: ${rs.baseline_fitness ?? "—"} · Promotions: ${rs.promotions || 0} · Rollbacks: ${rs.rollbacks || 0} · Quarantine: ${(d.quarantine || []).length}`));
    for (const s of ((d.agenda || {}).steps || [])) {
      aBox.append(el("div", { style: "color:var(--machine)" }, `[${s.status}] ${s.goal_kind} -> ${s.target_room || "any"} ${s.target_id || ""}`));
    }

    const kBox = document.getElementById("drawer-knobs");
    clear(kBox);
    const specs = (state.snapshot && state.snapshot.knob_specs) || {};
    const curKnobs = d.knobs || {};
    for (const [k, spec] of Object.entries(specs)) {
      const row = el("div", { class: "knob-row" });
      const val = curKnobs[k] ?? spec.default;
      const valSpan = el("span", {}, String(val));
      const slider = el("input", {
        type: "range",
        min: spec.min,
        max: spec.max,
        step: spec.is_int ? 1 : 0.05,
        value: val,
        "data-knob": k,
      });
      slider.oninput = () => { valSpan.textContent = slider.value; };
      row.append(el("span", {}, k), slider, valSpan);
      kBox.append(row);
    }

    const mBox = document.getElementById("drawer-memory");
    clear(mBox);
    for (const f of (d.facts || []).slice(0, 15)) {
      mBox.append(el("div", { class: "list-item" }, `[${f.kind} seq:${f.source_sequence || 0}] ${f.text}`));
    }
  } catch (err) {
    toast(err.message);
  }
}

async function controlUnit(unit, action) {
  try {
    const res = await apiPost("/api/control/unit", { unit, action });
    toast(res.message || `${action} ${unit}`);
    await refreshSnapshot();
  } catch (err) { toast(err.message); }
}

function applySnapshot(snap) {
  if (snap.map) {
    state.map = snap.map;
    state.mapSig = snap.map_sig || null;
  }
  state.snapshot = { ...snap, map: state.map };
  if (!state.turns.length && snap.recent_turns) state.turns = snap.recent_turns.slice(0, FEED_CAP);
  renderTopbar(state.snapshot);
  renderAgents(state.snapshot);
  renderReachMap(state.snapshot);
  if (!KIOSK) renderEconomyAndAudit(state.snapshot);
}

async function refreshSnapshot() {
  try {
    applySnapshot(await apiGet("/api/snapshot"));
    scheduleFeed();
  } catch (err) {
    toast(err.message);
  }
}

function connectSSE() {
  if (state.es) state.es.close();
  const params = new URLSearchParams();
  if (state.token) params.set("token", state.token);
  if (KIOSK) params.set("interval", "10");
  const qs = params.toString() ? "?" + params.toString() : "";
  const es = new EventSource("/api/stream" + qs);
  state.es = es;
  const pill = document.getElementById("conn-pill");

  es.onopen = () => {
    state.retryMs = 1500;
    state.lastEventTs = Date.now();
    pill.textContent = "SSE LIVE";
    pill.className = "pill pill-active";
  };

  es.addEventListener("snapshot", (ev) => {
    state.lastEventTs = Date.now();
    applySnapshot(JSON.parse(ev.data));
  });

  es.addEventListener("turn", (ev) => {
    state.lastEventTs = Date.now();
    const row = JSON.parse(ev.data);
    state.turns.unshift(row);
    if (state.turns.length > FEED_CAP) state.turns.length = FEED_CAP;
    scheduleFeed();
    const c = state.cards.get(row.member);
    if (c) {
      // Cheap pulse on the one card that moved; full card data arrives with the next snapshot.
      c.card.classList.add("pulse");
      clearTimeout(c.pulseT);
      c.pulseT = setTimeout(() => c.card.classList.remove("pulse"), 1200);
    }
  });

  es.onerror = () => {
    pill.textContent = "RECONNECTING";
    pill.className = "pill pill-warn";
    es.close();
    setTimeout(connectSSE, state.retryMs);
    state.retryMs = Math.min(15000, Math.round(state.retryMs * 1.6));
  };
}

function wireEvents() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll(".tab, .tab-body").forEach((x) => x.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
    };
  });

  document.getElementById("feed-filter").onchange = (ev) => {
    state.filter = ev.target.value;
    renderFeed();
  };
  const rolesChk = document.getElementById("feed-roles-only");
  if (rolesChk) {
    rolesChk.checked = state.rolesOnly;
    rolesChk.onchange = () => {
      state.rolesOnly = rolesChk.checked;
      renderFeed();
    };
  }

  document.getElementById("btn-auth").onclick = () => {
    showModal({
      title: "Operator Token",
      msg: "Optional bearer token for remote/control endpoints (stored locally in browser).",
      danger: false,
      input: true,
      onConfirm: async (val) => {
        state.token = val.trim();
        localStorage.setItem("noema_dash_token", state.token);
        await refreshSnapshot();
        connectSSE();
      },
    });
  };

  document.getElementById("btn-canary").onclick = () => {
    showModal({
      title: "Canary Rolling Restart",
      msg: "Restart m02 + m06 sequentially with live turn-gate verification?",
      danger: false,
      onConfirm: async () => {
        try {
          const r = await apiPost("/api/control/group", { action: "rolling_restart", preset: "canary" });
          toast(r.message || "Canary restart complete");
          await refreshSnapshot();
        } catch (err) { toast(err.message); }
      },
    });
  };

  document.getElementById("btn-roll").onclick = () => {
    showModal({
      title: "Full Fleet Rolling Restart",
      msg: "Restart m01..m06 + maint sequentially via deploy/rolling-restart.sh --apply?",
      danger: false,
      onConfirm: async () => {
        try {
          const r = await apiPost("/api/control/group", { action: "rolling_restart", preset: "full" });
          toast(r.message || "Rolling restart complete");
          await refreshSnapshot();
        } catch (err) { toast(err.message); }
      },
    });
  };

  document.getElementById("btn-estop").onclick = () => {
    showModal({
      title: "Emergency Group Stop",
      msg: "Immediately stop noema-players.target (all civic Players)?",
      danger: true,
      onConfirm: async () => {
        try {
          const r = await apiPost("/api/control/group", { action: "stop", preset: "full" });
          toast(r.message || "Group stopped");
          await refreshSnapshot();
        } catch (err) { toast(err.message); }
      },
    });
  };

  document.getElementById("btn-group-start").onclick = async () => {
    try {
      const r = await apiPost("/api/control/group", { action: "start", preset: "full" });
      toast(r.message || "Group started");
      await refreshSnapshot();
    } catch (err) { toast(err.message); }
  };

  document.getElementById("btn-save-mode").onclick = async () => {
    try {
      const r = await apiPost("/api/control/mode", {
        inference_mode: document.getElementById("sel-inf-mode").value,
        grounded_voice: document.getElementById("chk-voice").checked,
      });
      toast(`Saved mode: ${r.inference_mode}`);
      await refreshSnapshot();
    } catch (err) { toast(err.message); }
  };

  document.querySelectorAll("[data-ops]").forEach((btn) => {
    btn.onclick = async () => {
      const job = btn.dataset.ops;
      const out = document.getElementById("ops-output");
      out.textContent = `Running ${job}...`;
      try {
        const r = await apiPost("/api/control/ops", { job });
        out.textContent = JSON.stringify(r.result || r.output || r, null, 2);
        toast(`Ops ${job} ok`);
        await refreshSnapshot();
      } catch (err) {
        out.textContent = "ERROR: " + err.message;
        toast(err.message);
      }
    };
  });

  document.getElementById("drawer-close").onclick = () => document.getElementById("drawer").classList.add("hidden");
  document.getElementById("drawer-restart").onclick = () => state.selectedMember && controlUnit(`noema-player@${state.selectedMember}`, "restart");
  document.getElementById("drawer-stop").onclick = () => state.selectedMember && controlUnit(`noema-player@${state.selectedMember}`, "stop");
  document.getElementById("drawer-refresh-agenda").onclick = async () => {
    if (!state.selectedMember) return;
    try {
      await apiPost(`/api/control/agenda/${state.selectedMember}`, {});
      toast("Agenda marked for refresh");
      await openDrawer(state.selectedMember);
    } catch (err) { toast(err.message); }
  };

  document.querySelectorAll("[data-rsi]").forEach((btn) => {
    btn.onclick = async () => {
      if (!state.selectedMember) return;
      try {
        await apiPost(`/api/control/rsi/${state.selectedMember}`, { action: btn.dataset.rsi });
        toast(`RSI ${btn.dataset.rsi} applied`);
        await openDrawer(state.selectedMember);
        await refreshSnapshot();
      } catch (err) { toast(err.message); }
    };
  });

  document.getElementById("drawer-save-knobs").onclick = async () => {
    if (!state.selectedMember) return;
    const patch = {};
    document.querySelectorAll("#drawer-knobs input[data-knob]").forEach((inp) => {
      const k = inp.dataset.knob;
      const spec = (state.snapshot.knob_specs || {})[k] || {};
      patch[k] = spec.is_int ? parseInt(inp.value, 10) : parseFloat(inp.value);
    });
    try {
      await apiPost(`/api/control/knobs/${state.selectedMember}`, patch);
      toast("Clamped knobs saved");
      await openDrawer(state.selectedMember);
      await refreshSnapshot();
    } catch (err) { toast(err.message); }
  };

  document.getElementById("btn-mem-search").onclick = () => {
    if (state.selectedMember) openDrawer(state.selectedMember, document.getElementById("mem-search").value);
  };

  // Subtle 2px anti-burn-in micro-drift for 24/7 kiosk monitors (?kiosk=1)
  if (new URLSearchParams(window.location.search).get("kiosk") === "1") {
    let step = 0;
    setInterval(() => {
      step = (step + 1) % 4;
      const dx = step === 1 ? 2 : step === 3 ? -2 : 0;
      const dy = step === 2 ? 2 : 0;
      document.getElementById("app").style.transform = `translate(${dx}px, ${dy}px)`;
    }, 300000);
  }
}

wireEvents();
refreshSnapshot();
connectSSE();
