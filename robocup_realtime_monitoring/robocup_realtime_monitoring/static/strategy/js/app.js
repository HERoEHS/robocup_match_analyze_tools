import { Court } from "./court.js";
import { ZoneLayer } from "./zones.js";
import { ActionPanel } from "./action-panel.js";
import { LayerPanel } from "./layer-panel.js";
import { DefaultsPanel } from "./defaults-panel.js";
import { LiveLayer } from "./live-layer.js";
import { LiveStatusPanel } from "./live-status.js";
import { t, getLang, setLang, initLang, applyToDOM, onLangChange } from "./i18n.js";

const state = {
  version: 1,
  field: null,
  defaults: null,
  zones: [],
  selectedId: null,
  hiddenIds: new Set(),
  dirty: false,
};

let court = null;
let zoneLayer = null;
let actionPanel = null;
let layerPanel = null;
let defaultsPanel = null;
let liveLayer = null;
let liveStatusPanel = null;

const robotLayerStore = {
  _m: new Map(),
  _entry(id) {
    let v = this._m.get(id);
    if (!v) { v = { ownBall: false, fusedBall: true, fusedEnemy: true }; this._m.set(id, v); }
    return v;
  },
  isOn(id, key) { return !!this._entry(id)[key]; },
  toggle(id, key) {
    const v = this._entry(id);
    v[key] = !v[key];
    if (liveLayer) liveLayer.redraw();
    return v[key];
  },
};

// ─── Live position overlay polling ────────────────────────────────
const LIVE_POLL_MS = 150;
const LIVE_CONN_STALE_MS = 1500;
let liveEnabled = true;
let liveTimer = null;
let liveInFlight = false;
let lastLiveOkMs = 0;
let _lastLiveData = null;
let _liveDisconnected = false;

// ─── Action classification: move_to / turn_to / kick ──────────────
const INTENT_MIN_M = 0.15;
const KICK_BALL_SPEED_MIN = 1.0;
const KICK_BALL_SPEED_MAX = 12.0;
const GOAL_AIM_X_MARGIN = 1.5;
const GOAL_AIM_Y_MARGIN = 1.0;
const GOAL_AIM_BALL_FAR_M = 1.0;
const KICK_NEAR_BALL_M = 0.7;
const KICK_HOLD_S = 1.0;
let _ballPrev = null;
let _kickHold = null;

function _ballMovingNow(ball, nowSec) {
  if (!ball || typeof ball.x !== "number" || typeof ball.y !== "number") {
    _ballPrev = null;
    return { moving: false, fromX: null, fromY: null };
  }
  let moving = false;
  const prev = _ballPrev;
  if (prev) {
    const dt = nowSec - prev.t;
    if (dt > 1e-3) {
      const sp = Math.hypot(ball.x - prev.x, ball.y - prev.y) / dt;
      moving = sp >= KICK_BALL_SPEED_MIN && sp <= KICK_BALL_SPEED_MAX;
    }
  }
  const fromX = prev ? prev.x : ball.x;
  const fromY = prev ? prev.y : ball.y;
  _ballPrev = { x: ball.x, y: ball.y, t: nowSec };
  return { moving, fromX, fromY };
}

function _isGoalAim(w, ball, field) {
  if (!w || typeof w.x !== "number" || typeof w.y !== "number") return false;
  const goalLineX = (field && field.length_m ? field.length_m : 14) / 2;
  const goalHalf =
    (field && field.goal && field.goal.inner_width_m ? field.goal.inner_width_m : 2.4) / 2;
  const nearGoal =
    w.x >= goalLineX - GOAL_AIM_X_MARGIN && Math.abs(w.y) <= goalHalf + GOAL_AIM_Y_MARGIN;
  if (!nearGoal) return false;
  if (ball && typeof ball.x === "number"
      && Math.hypot(w.x - ball.x, w.y - ball.y) <= GOAL_AIM_BALL_FAR_M) {
    return false;
  }
  return true;
}


async function pollLiveOnce() {
  if (!liveEnabled || liveInFlight || !liveLayer) return;
  liveInFlight = true;
  try {
    const r = await fetch("/api/live", { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    lastLiveOkMs = performance.now();
    _liveDisconnected = false;
    _lastLiveData = data;
    liveLayer.render(data);
    if (liveStatusPanel) liveStatusPanel.render(data);
    updateLiveStatus(data);
  } catch (_e) {
    if (liveLayer && performance.now() - lastLiveOkMs > LIVE_CONN_STALE_MS) {
      _liveDisconnected = true;
      _lastLiveData = null;
      liveLayer.clear();
      liveLayer.resetTrails();
      _ballPrev = null;
      _kickHold = null;
      if (liveStatusPanel) liveStatusPanel.clear();
      const el = document.getElementById("live-status");
      if (el) el.textContent = t("live-status-disconnected");
    }
  } finally {
    liveInFlight = false;
  }
}

function startLivePolling() {
  if (liveTimer) return;
  lastLiveOkMs = performance.now();
  liveTimer = setInterval(pollLiveOnce, LIVE_POLL_MS);
  pollLiveOnce();
}

function stopLivePolling() {
  if (liveTimer) {
    clearInterval(liveTimer);
    liveTimer = null;
  }
}

function setLiveEnabled(on) {
  liveEnabled = on;
  if (on) {
    lastLiveOkMs = performance.now();
    _liveDisconnected = false;
    startLivePolling();
    pollLiveOnce();
  } else {
    stopLivePolling();
    if (liveLayer) { liveLayer.clear(); liveLayer.resetTrails(); }
    _ballPrev = null;
    _kickHold = null;
    _lastLiveData = null;
    _liveDisconnected = false;
    if (liveStatusPanel) liveStatusPanel.clear();
    updateLiveStatus(null);
  }
}

function updateLiveStatus(data) {
  const el = document.getElementById("live-status");
  if (!el) return;
  if (!liveEnabled) { el.textContent = t("live-status-off"); return; }
  if (_liveDisconnected) { el.textContent = t("live-status-disconnected"); return; }
  if (!data || data.enabled === false) {
    el.textContent = t("live-status-no-data");
    return;
  }
  const n = (data.robots || []).length;
  const ball = data.ball ? t("ball-o") : t("ball-x");
  el.textContent = t("live-status-active", n, ball);
}

async function fetchJson(url, init) {
  const r = await fetch(url, init);
  if (!r.ok) {
    const txt = await r.text();
    throw new Error(`${r.status} ${r.statusText}: ${txt}`);
  }
  return r.json();
}

function setSaveStatus(msg, isError = false) {
  const el = document.getElementById("save-status");
  el.textContent = msg;
  el.style.color = isError ? "#cf222e" : "var(--muted)";
}

function markDirty() {
  state.dirty = true;
  setSaveStatus(t("save-dirty"));
}

function getZoneById(id) {
  return state.zones.find((z) => z.id === id) || null;
}

function isHidden(id) { return state.hiddenIds.has(id); }

function toggleHidden(id) {
  if (state.hiddenIds.has(id)) state.hiddenIds.delete(id);
  else state.hiddenIds.add(id);
  zoneLayer.render();
  layerPanel.render();
  updateToggleAllLabel();
}

function setAllZonesHidden(hidden) {
  if (hidden) {
    for (const z of state.zones) state.hiddenIds.add(z.id);
  } else {
    state.hiddenIds.clear();
  }
  zoneLayer.render();
  layerPanel.render();
  updateToggleAllLabel();
}

function updateToggleAllLabel() {
  const btn = document.getElementById("btn-toggle-all-layers");
  if (!btn) return;
  const total = state.zones.length;
  const hiddenCount = state.zones.reduce(
    (n, z) => n + (state.hiddenIds.has(z.id) ? 1 : 0), 0,
  );
  const allHidden = total > 0 && hiddenCount === total;
  btn.textContent = t(allHidden ? "show-all" : "hide-all");
  btn.disabled = total === 0;
}

function selectZone(id) {
  state.selectedId = id;
  document.getElementById("selected-id").textContent = id || t("selected-none");
  actionPanel.show(getZoneById(id));
  updateZorderInfo();
  zoneLayer.render();
  layerPanel.render();
}

function updateZorderInfo() {
  const info = document.getElementById("zorder-info");
  if (!info) return;
  if (!state.selectedId) { info.textContent = ""; return; }
  const idx = state.zones.findIndex((z) => z.id === state.selectedId);
  info.textContent = `${idx + 1} / ${state.zones.length}`;
}

function onMutate(change) {
  markDirty();
  if (change && change.kind === "defaults") {
    court.setBgHint(state.defaults?.global?.action);
  }
  actionPanel.show(getZoneById(state.selectedId));
  updateZorderInfo();
  zoneLayer.render();
  layerPanel.render();
  defaultsPanel.render();
  updateToggleAllLabel();
}

function onCursor(pt) {
  document.getElementById("mouse-coord").textContent =
    `x=${pt.x.toFixed(2)}  y=${pt.y.toFixed(2)}`;
}

// ─── REST ────────────────────────────────────────────────────

async function loadAll() {
  const [field, payload, pathInfo] = await Promise.all([
    fetchJson("/api/field_config"),
    fetchJson("/api/zones"),
    fetchJson("/api/zones/path"),
  ]);
  state.field = field;
  state.version = payload.version || 1;
  state.zones = payload.zones || [];
  state.defaults = payload.defaults || {
    global: { action: "none" },
    local:  { action: "none" },
  };
  state.hiddenIds = new Set();
  state.dirty = false;
  document.getElementById("yaml-path-display").textContent = pathInfo.path;
  setSaveStatus(t("save-loaded"));
}

async function saveAll() {
  try {
    if (defaultsPanel) defaultsPanel.apply({ silent: true });

    const payload = {
      version: state.version,
      field: state.field,
      defaults: state.defaults,
      zones: state.zones,
    };
    const res = await fetchJson("/api/zones", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.dirty = false;
    setSaveStatus(t("save-saved", res.zone_count));
  } catch (e) {
    setSaveStatus(`✗ ${e.message}`, true);
  }
}

// ─── Zone CRUD + z-order ─────────────────────────────────────

function addZone(type) {
  let i = 1;
  while (getZoneById(`new_zone_${i}`)) i += 1;
  const id = `new_zone_${i}`;
  const z = {
    id,
    name: t("new-zone-name", i),
    type,
    space: "global",
    bt_ref: "",
    color: type === "rect" ? "#f1c40f" : "#16a085",
    action_policy: { action: "none" },
    geometry: type === "rect"
      ? { x1: -1.0, y1: -1.0, x2: 1.0, y2: 1.0 }
      : { cx: 0.0, cy: 0.0, r: 1.0 },
  };
  state.zones.push(z);
  selectZone(id);
  markDirty();
  zoneLayer.render();
  layerPanel.render();
  updateToggleAllLabel();
}

function reorder(action) {
  const id = state.selectedId;
  if (!id) return;
  const i = state.zones.findIndex((z) => z.id === id);
  if (i < 0) return;
  const arr = state.zones;
  if (action === "front") {
    if (i === arr.length - 1) return;
    arr.push(arr.splice(i, 1)[0]);
  } else if (action === "back") {
    if (i === 0) return;
    arr.unshift(arr.splice(i, 1)[0]);
  } else if (action === "forward") {
    if (i === arr.length - 1) return;
    [arr[i], arr[i + 1]] = [arr[i + 1], arr[i]];
  } else if (action === "backward") {
    if (i === 0) return;
    [arr[i], arr[i - 1]] = [arr[i - 1], arr[i]];
  }
  markDirty();
  updateZorderInfo();
  zoneLayer.render();
  layerPanel.render();
}

// ─── Main bootstrap ──────────────────────────────────────────

async function main() {
  initLang();
  await loadAll();

  const svg = document.getElementById("court");
  court = new Court(svg, state.field);

  const store = {
    get zones() { return state.zones; },
    get selectedId() { return state.selectedId; },
    set selectedId(v) { state.selectedId = v; },
    get defaults() { return state.defaults; },
    set defaults(v) { state.defaults = v; },
    isHidden,
    toggleHidden,
    selectZone,
    onSelect: selectZone,
    onMutate,
    onCursor,
  };

  zoneLayer = new ZoneLayer(svg, court, store);
  liveLayer = new LiveLayer(svg, court);
  liveLayer.robotLayers = robotLayerStore;
  liveStatusPanel = new LiveStatusPanel(
    document.getElementById("robot-status-list"),
    document.getElementById("robot-status-count"),
    document.getElementById("robot-status-empty"),
    robotLayerStore,
  );

  actionPanel = new ActionPanel(
    document.getElementById("zone-form"),
    document.getElementById("panel-empty"),
    store,
  );

  layerPanel = new LayerPanel(
    document.getElementById("layer-list"),
    document.getElementById("layer-count"),
    store,
  );

  defaultsPanel = new DefaultsPanel({
    form: document.getElementById("defaults-form"),
    tabs: document.querySelectorAll(".defaults-tab"),
    toggleBtn: document.getElementById("defaults-toggle"),
    card: document.getElementById("defaults-card"),
    store,
  });

  court.onResize(() => {
    court.setBgHint(state.defaults?.global?.action);
    zoneLayer.render();
    if (liveLayer) liveLayer.redraw();
  });
  court.setBgHint(state.defaults?.global?.action);
  zoneLayer.render();
  layerPanel.render();
  defaultsPanel.render();
  updateToggleAllLabel();
  selectZone(null);
  updateLiveStatus(null);

  // ─── Left/right panel collapse toggle ─────────────────────────
  const layoutEl = document.getElementById("layout");
  const refitCourt = () => {
    window.dispatchEvent(new Event("resize"));
    setTimeout(() => window.dispatchEvent(new Event("resize")), 180);
  };
  const btnLeft = document.getElementById("btn-toggle-left");
  if (btnLeft) {
    btnLeft.title = t("toggle-left-collapse");
    btnLeft.addEventListener("click", () => {
      const collapsed = layoutEl.classList.toggle("left-collapsed");
      btnLeft.textContent = collapsed ? "▶" : "◀";
      btnLeft.title = t(collapsed ? "toggle-left-expand" : "toggle-left-collapse");
      refitCourt();
    });
  }
  const btnRight = document.getElementById("btn-toggle-right");
  if (btnRight) {
    btnRight.title = t("toggle-right-collapse");
    btnRight.addEventListener("click", () => {
      const collapsed = layoutEl.classList.toggle("right-collapsed");
      btnRight.textContent = collapsed ? "◀" : "▶";
      btnRight.title = t(collapsed ? "toggle-right-expand" : "toggle-right-collapse");
      refitCourt();
    });
  }

  // Live position overlay toggle + polling start
  const liveToggle = document.getElementById("live-toggle");
  if (liveToggle) {
    liveEnabled = liveToggle.checked;
    liveToggle.addEventListener("change", () => setLiveEnabled(liveToggle.checked));
  }
  if (liveEnabled) startLivePolling();
  else updateLiveStatus(null);

  // ─── SVG body mousedown: empty area click + Alt+click cycle ──
  svg.addEventListener("mousedown", (e) => {
    if (e.altKey || e.shiftKey) {
      e.preventDefault();
      const pt = court.mFromClient(e.clientX, e.clientY);
      zoneLayer.cycleSelectAt(pt.x, pt.y);
      return;
    }
    if (e.target === svg) selectZone(null);
  });

  // ─── Buttons ────────────────────────────────────────────────
  document.getElementById("btn-add-rect").addEventListener("click", () => addZone("rect"));
  document.getElementById("btn-add-circle").addEventListener("click", () => addZone("circle"));
  document.getElementById("btn-save").addEventListener("click", saveAll);
  document.getElementById("btn-reload").addEventListener("click", async () => {
    if (state.dirty && !confirm(t("confirm-reload"))) return;
    await loadAll();
    selectZone(null);
    court.setBgHint(state.defaults?.global?.action);
    zoneLayer.render();
    layerPanel.render();
    defaultsPanel.render();
    updateToggleAllLabel();
  });

  document.getElementById("btn-z-front").addEventListener("click",   () => reorder("front"));
  document.getElementById("btn-z-forward").addEventListener("click", () => reorder("forward"));
  document.getElementById("btn-z-backward").addEventListener("click",() => reorder("backward"));
  document.getElementById("btn-z-back").addEventListener("click",    () => reorder("back"));

  const toggleAllBtn = document.getElementById("btn-toggle-all-layers");
  if (toggleAllBtn) {
    toggleAllBtn.addEventListener("click", () => {
      const total = state.zones.length;
      const hiddenCount = state.zones.reduce(
        (n, z) => n + (state.hiddenIds.has(z.id) ? 1 : 0), 0,
      );
      const allHidden = total > 0 && hiddenCount === total;
      setAllZonesHidden(!allHidden);
    });
  }

  // ─── Language toggle ────────────────────────────────────────
  const langBtn = document.getElementById("btn-lang-toggle");
  if (langBtn) {
    langBtn.addEventListener("click", () => setLang(getLang() === "ko" ? "en" : "ko"));
  }

  // ─── Language change: re-apply dynamic text ─────────────────
  onLangChange(() => {
    applyToDOM();
    updateToggleAllLabel();
    selectZone(state.selectedId);
    updateLiveStatus(_lastLiveData);
    if (zoneLayer) zoneLayer.render();
    if (btnLeft) {
      const collapsed = layoutEl.classList.contains("left-collapsed");
      btnLeft.title = t(collapsed ? "toggle-left-expand" : "toggle-left-collapse");
    }
    if (btnRight) {
      const collapsed = layoutEl.classList.contains("right-collapsed");
      btnRight.title = t(collapsed ? "toggle-right-expand" : "toggle-right-collapse");
    }
  });

  window.addEventListener("beforeunload", (e) => {
    if (state.dirty) { e.preventDefault(); e.returnValue = ""; }
  });

  document.getElementById("btn-goto-replay").addEventListener("click", () => {
    if (state.dirty && !confirm(t("confirm-leave"))) return;
    window.location.href = `${window.location.protocol}//${window.location.hostname}:8095/`;
  });
}

main().catch((e) => {
  console.error(e);
  setSaveStatus(t("save-init-failed", e.message), true);
});
