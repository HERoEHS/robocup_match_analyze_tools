import { colorForRobot } from "./live-layer.js";
import { t, onLangChange } from "./i18n.js";

const CONF_GOOD_M = 0.15;
const CONF_WARN_M = 0.40;

const ACTION_CLS = {
  move_to: "move",
  turn_to: "turn",
  kick: "kick",
  pass: "pass",
  dribble: "dribble",
  stop_move: "stop",
  spin_search: "search",
  recheck_wait: "wait",
  save_ball_to_destination: "save",
  mark_buildup_passed: "mark",
  reset_buildup_pass: "reset",
};

function actionLabel(action) {
  if (!action) return { text: "—", cls: "unknown" };
  const key = `act-${action}`;
  const text = t(key);
  return { text: text === key ? "—" : text, cls: ACTION_CLS[action] || "unknown" };
}

function rad2deg(r) { return (r * 180) / Math.PI; }

function confidenceFromCov(cov) {
  if (!cov) return { sigma: null, cls: "unknown", label: "—" };
  const sigma = Math.hypot(cov.x || 0, cov.y || 0);
  if (sigma <= 0) return { sigma: 0, cls: "unknown", label: "—" };
  let cls = "bad";
  if (sigma <= CONF_GOOD_M) cls = "good";
  else if (sigma <= CONF_WARN_M) cls = "warn";
  return { sigma, cls, label: `±${sigma.toFixed(2)}m` };
}

export class LiveStatusPanel {
  constructor(listEl, countEl, emptyEl, overlay) {
    this.list = listEl;
    this.countEl = countEl;
    this.emptyEl = emptyEl;
    this.overlay = overlay || null;
    this._cards = new Map();

    // Clear card cache on language change so they're rebuilt with new t() values.
    onLangChange(() => {
      this.list.innerHTML = "";
      this._cards.clear();
      if (this.countEl) this.countEl.textContent = "(0)";
      if (this.emptyEl) this.emptyEl.style.display = "";
    });
  }

  render(data) {
    const robots = data && Array.isArray(data.robots) ? data.robots : [];
    if (this.countEl) this.countEl.textContent = `(${robots.length})`;

    if (!robots.length) {
      this.clear();
      return;
    }
    if (this.emptyEl) this.emptyEl.style.display = "none";

    const seen = new Set();
    for (const r of robots) {
      if (r == null || r.id == null) continue;
      seen.add(r.id);
      let card = this._cards.get(r.id);
      if (!card) {
        card = this._createCard(r);
        this._cards.set(r.id, card);
      }
      this._updateCard(card, r);
      this.list.appendChild(card.li);
    }
    for (const [id, card] of this._cards) {
      if (!seen.has(id)) {
        card.li.remove();
        this._cards.delete(id);
      }
    }
  }

  clear() {
    this.list.innerHTML = "";
    this._cards.clear();
    if (this.countEl) this.countEl.textContent = "(0)";
    if (this.emptyEl) this.emptyEl.style.display = "";
  }

  _createCard(r) {
    const color = colorForRobot(r.id);
    const li = document.createElement("li");
    li.className = "rs-card";
    li.style.borderLeftColor = color;

    const head = document.createElement("div");
    head.className = "rs-head";

    const dot = document.createElement("span");
    dot.className = "rs-dot";
    dot.style.background = color;
    head.appendChild(dot);

    const name = document.createElement("span");
    name.className = "rs-name";
    name.textContent = r.name || `robot${r.id}`;
    head.appendChild(name);

    const conn = document.createElement("span");
    conn.className = "rs-badge";
    conn.title = t("conn-title");
    head.appendChild(conn);

    const pen = document.createElement("span");
    pen.className = "rs-badge bad";
    pen.textContent = "PEN";
    pen.title = t("pen-title");
    pen.style.display = "none";
    head.appendChild(pen);

    const comm = document.createElement("span");
    comm.className = "rs-badge";
    comm.textContent = t("comm-label");
    head.appendChild(comm);
    li.appendChild(head);

    const body = document.createElement("div");
    body.className = "rs-body";
    const actRow = this._row(t("row-action"), "—");
    const poseRow = this._row(t("row-pose"), "—");
    const confRow = this._row(t("row-conf"), "—");
    const ballRow = this._row(t("row-ball"), "—");
    const ballposRow = this._row(t("row-ballpos"), "—");
    body.appendChild(actRow);
    body.appendChild(poseRow);
    body.appendChild(confRow);
    body.appendChild(ballRow);
    body.appendChild(ballposRow);
    li.appendChild(body);

    const refs = {
      li, conn, pen, comm,
      actVal: actRow.querySelector(".rs-val"),
      poseVal: poseRow.querySelector(".rs-val"),
      confVal: confRow.querySelector(".rs-val"),
      ballVal: ballRow.querySelector(".rs-val"),
      ballposVal: ballposRow.querySelector(".rs-val"),
      toggles: {},
    };

    if (this.overlay) {
      const tg = document.createElement("div");
      tg.className = "rs-toggles";
      const defs = [
        ["ownBall", t("tgl-own-ball")],
        ["fusedBall", t("tgl-fused-ball")],
        ["fusedEnemy", t("tgl-fused-enemy")],
      ];
      for (const [key, text] of defs) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "rs-toggle";
        b.textContent = text;
        b.addEventListener("click", () => {
          const nowOn = this.overlay.toggle(r.id, key);
          b.classList.toggle("on", nowOn);
          b.title = t(nowOn ? "overlay-on-fmt" : "overlay-off-fmt", text);
        });
        refs.toggles[key] = { btn: b, text };
        tg.appendChild(b);
      }
      li.appendChild(tg);
    }
    return refs;
  }

  _updateCard(card, r) {
    const fresh = typeof r.age === "number" ? r.age <= 0.6 : true;
    card.conn.className = "rs-badge " + (fresh ? "ok" : "stale");
    card.conn.textContent = typeof r.age === "number" ? `${r.age.toFixed(1)}s` : "live";

    card.pen.style.display = r.penalty ? "" : "none";

    card.comm.className = "rs-badge " + (r.comm ? "ok" : "bad");
    card.comm.title = t(r.comm ? "comm-ok-title" : "comm-bad-title");

    const act = actionLabel(r.action);
    card.actVal.textContent = act.text;
    card.actVal.className = "rs-val rs-action " + act.cls;
    card.actVal.title = t("act-val-title");

    card.poseVal.textContent = `x ${num(r.x)}  y ${num(r.y)}  θ ${degOf(r.theta)}°`;

    const conf = confidenceFromCov(r.cov);
    card.confVal.textContent = conf.label;
    card.confVal.className = "rs-val rs-conf " + conf.cls;
    if (r.eval) {
      card.confVal.title =
        `eval mc=${num3(r.eval.mc)} vslam=${num3(r.eval.vslam)}\n` +
        `σ x=${num(r.cov?.x)} y=${num(r.cov?.y)} θ=${num3(r.cov?.theta)}`;
    }

    card.ballVal.textContent = t(r.ball_detected ? "ball-detecting" : "ball-not-detecting");
    card.ballVal.style.color = r.ball_detected ? "#30a46c" : "#e5484d";
    card.ballVal.style.fontWeight = "600";

    const bp = r.ball_pos;
    card.ballposVal.textContent = bp ? `x ${num(bp.x)}  y ${num(bp.y)}` : "—";

    if (this.overlay) {
      for (const key of Object.keys(card.toggles)) {
        const { btn, text } = card.toggles[key];
        const on = this.overlay.isOn(r.id, key);
        btn.classList.toggle("on", on);
        btn.title = t(on ? "overlay-on-fmt" : "overlay-off-fmt", text);
      }
    }
  }

  _row(label, value) {
    const row = document.createElement("div");
    row.className = "rs-row";
    const k = document.createElement("span");
    k.className = "rs-key";
    k.textContent = label;
    const v = document.createElement("span");
    v.className = "rs-val";
    v.textContent = value;
    row.appendChild(k);
    row.appendChild(v);
    return row;
  }
}

function num(x) { return typeof x === "number" ? x.toFixed(2) : "—"; }
function num3(x) { return typeof x === "number" ? x.toFixed(3) : "—"; }
function degOf(th) { return typeof th === "number" ? rad2deg(th).toFixed(0) : "—"; }
