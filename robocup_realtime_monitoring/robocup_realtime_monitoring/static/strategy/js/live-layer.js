import { t } from "./i18n.js";

const SVGNS = "http://www.w3.org/2000/svg";
const XLINKNS = "http://www.w3.org/1999/xlink";

// Marker images for fused overlays.
const BALL_IMG = "/img/markers/soccer_ball.png";
const ENEMY_IMG = "/img/markers/devil.png";

// robotN color palette (id -> color). Out-of-range IDs get a hashed fallback color.
const ROBOT_COLORS = {
  1: "#00e5ff", // robot1 cyan
  2: "#ffca28", // robot2 amber
  3: "#ff5d8f", // robot3 pink
  4: "#7cff6b", // robot4 green
  5: "#b388ff", // robot5 purple
};

export function colorForRobot(id) {
  if (ROBOT_COLORS[id]) return ROBOT_COLORS[id];
  const hue = (id * 67) % 360;
  return `hsl(${hue}, 80%, 60%)`;
}

export class LiveLayer {
  /**
   * @param {SVGSVGElement} svgEl
   * @param {import('./court.js').Court} court
   */
  constructor(svgEl, court) {
    this.svg = svgEl;
    this.court = court;
    this.fadeAge = 0.6;   // Fade after this age.
    this.staleAge = 2.0;  // Hide after this age (used together with backend stale_sec).
    this._group = null;
    this._lastData = null;

    // ─── trail ────────────────────────────────────
    this.showTrail = true;
    this.trailSeconds = 15.0;   // Drop points older than this many seconds.
    this.trailMinStepM = 0.03;  // Add points only after this much movement.
    this.trailMaxPoints = 300;  
    this._trails = new Map();

    // Opponents (vision-detected opponent robots)
    // Off by default because the fused-enemy overlay replaces it.
    // Enable to also show raw merged opponents (red diamonds).
    this.showOpponents = false;
    this.opponentColor = "#e5484d"; // red

    // ─── intent ─────────────────────────────────────
    this.showIntent = true;
    this.intentColor = "#22c55e";
    this.intentMinM = 0.15;      // Draw only when the goal point is at least this far away.

    // Balls (merge per-robot balls within 0.3 m, color by observer count/confidence)
    // Off by default because fused-ball / own-ball overlays replace it.
    // Enable to also show raw merged balls.
    this.showBalls = false;
    this.ballColor1 = "#ff7a00"; // single robot (legacy orange)
    this.ballColor2 = "#f5d90a"; // overlap from 2 robots (yellow)
    this.ballColor3 = "#30a46c"; // overlap from 3 robots (green)
    this.ballColor4 = "#0090ff"; // overlap from 4+ robots (blue)

    // Per-robot fused overlays (toggled from the sidebar, off by default)
    // robotLayers: {isOn(id,key), toggle(id,key)} injected by app.js.
    // key in ownBall/fusedBall/fusedEnemy.
    // If null, disable all overlays (same as the previous behavior).
    this.robotLayers = null;
    // Green gets lost against the grass, so self-seen markers use magenta;
    // teammate-only observations use yellow.
    this.selfSeenColor = "#e5009a"; // magenta = fused result including self
    this.teamSeenColor = "#f5d90a"; // yellow = visible only through teammates
  }

  /** Reset trail history (call on disconnect/reset). */
  resetTrails() {
    this._trails.clear();
  }

  _ensureGroup() {
    // Keep it as the last child so it always renders above zones.
    if (!this._group || !this._group.isConnected) {
      this._group = document.createElementNS(SVGNS, "g");
      this._group.setAttribute("id", "live-layer");
      this._group.setAttribute("pointer-events", "none"); // Never interfere with editing clicks.
    }
    if (this.svg.lastChild !== this._group) {
      this.svg.appendChild(this._group);
    }
    return this._group;
  }

  clear() {
    if (this._group) {
      while (this._group.firstChild) this._group.removeChild(this._group.firstChild);
    }
  }

  /** Redraw the last data when coordinates need recalculation, such as after resize. */
  redraw() {
    if (this._lastData) this.render(this._lastData);
  }

  /**
   * @param {{enabled?:boolean, robots?:Array, ball?:Object|null}} data
   */
  render(data) {
    this._lastData = data;
    const g = this._ensureGroup();
    // Rebuild everything each tick for simplicity and safety.
    this.clear();

    if (!data || data.enabled === false) return;
    if (!this.court || !this.court.scale) return;

    const robots = Array.isArray(data.robots) ? data.robots : [];
    const nowSec = performance.now() / 1000;

    if (this.showTrail) {
      this._updateTrails(robots, nowSec);
      for (const r of robots) {
        if (r == null || r.id == null) continue;
        const path = this._trailPath(r.id);
        if (path) g.appendChild(path);
      }
    }

    for (const r of robots) {
      if (r == null || typeof r.x !== "number" || typeof r.y !== "number") continue;
      if (typeof r.age === "number" && r.age > this.staleAge) continue;
      // Show the target arrow only while moving (move_to).
      if (this.showIntent && r.action === "move_to") {
        const arrow = this._intentArrow(r);
        if (arrow) g.appendChild(arrow);
      }
    }

    // Legacy merged opponents (red diamonds), hidden by default.
    // Replaced by the fused-enemy overlay.
    if (this.showOpponents) {
      const opponents = Array.isArray(data.opponents) ? data.opponents : [];
      for (const o of opponents) {
        if (o == null || typeof o.x !== "number" || typeof o.y !== "number") continue;
        g.appendChild(this._opponentMarker(o));
      }
    }

    for (const r of robots) {
      if (r == null || typeof r.x !== "number" || typeof r.y !== "number") continue;
      if (typeof r.age === "number" && r.age > this.staleAge) continue;
      g.appendChild(this._robotMarker(r));
    }

    // Legacy merged balls (soccer ball + robotN label), hidden by default.
    // Replaced by fused-ball / own-ball overlays.
    if (this.showBalls) {
      const balls = Array.isArray(data.balls)
        ? data.balls
        : (data.ball ? [data.ball] : []);
      for (const ball of balls) {
        if (!(typeof ball.x === "number" && typeof ball.y === "number")) continue;
        if (typeof ball.age === "number" && ball.age > this.staleAge) continue;
        g.appendChild(this._ballMarker(ball));
      }
    }

    // Per-robot fused overlays (sidebar toggles, off by default to match the prior UI)
    const layers = this.robotLayers;
    if (layers) {
      for (const r of robots) {
        if (r == null || r.id == null) continue;
        if (typeof r.age === "number" && r.age > this.staleAge) continue;
        // Ball seen directly by this robot (raw own ball = ball_pos).
        if (layers.isOn(r.id, "ownBall")
            && r.ball_pos && typeof r.ball_pos.x === "number") {
          g.appendChild(this._ownBallMarker(r));
        }
        // Fused ball (magenta=self included/direct, yellow=teammate-only).
        if (layers.isOn(r.id, "fusedBall")
            && r.fused_ball && typeof r.fused_ball.x === "number") {
          g.appendChild(this._fusedBallMarker(r));
        }
        // Fused enemies (up to 3, anonymous).
        if (layers.isOn(r.id, "fusedEnemy") && Array.isArray(r.fused_enemies)) {
          for (const en of r.fused_enemies) {
            if (en == null || typeof en.x !== "number") continue;
            g.appendChild(this._fusedEnemyMarker(r, en));
          }
        }
      }
    }
  }

  // Trail history
  _updateTrails(robots, nowSec) {
    for (const r of robots) {
      if (r == null || r.id == null) continue;
      if (typeof r.x !== "number" || typeof r.y !== "number") continue;
      if (typeof r.age === "number" && r.age > this.staleAge) continue;
      let hist = this._trails.get(r.id);
      if (!hist) { hist = []; this._trails.set(r.id, hist); }
      const last = hist[hist.length - 1];
      if (!last || Math.hypot(r.x - last.x, r.y - last.y) >= this.trailMinStepM) {
        hist.push({ x: r.x, y: r.y, t: nowSec });
      }
    }
    for (const [id, hist] of this._trails) {
      while (hist.length && nowSec - hist[0].t > this.trailSeconds) hist.shift();
      if (hist.length > this.trailMaxPoints) {
        hist.splice(0, hist.length - this.trailMaxPoints);
      }
      if (hist.length === 0) this._trails.delete(id);
    }
  }

  _trailPath(id) {
    const hist = this._trails.get(id);
    if (!hist || hist.length < 2) return null;
    const court = this.court;
    const pts = hist
      .map((h) => { const p = court.pxFromM(h.x, h.y); return `${p.sx},${p.sy}`; })
      .join(" ");
    const line = document.createElementNS(SVGNS, "polyline");
    line.setAttribute("class", "live-trail");
    line.setAttribute("points", pts);
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", colorForRobot(id));
    line.setAttribute("stroke-width", "3");
    line.setAttribute("stroke-opacity", "0.85");
    line.setAttribute("stroke-linecap", "round");
    line.setAttribute("stroke-linejoin", "round");
    line.setAttribute("stroke-dasharray", "4 4");
    return line;
  }

  /**
   * Arrow: solid green line to walk_command (global target point) plus target marker.
   * Skip it when the target is almost the current position. Return null if wcmd is missing.
   */
  _intentArrow(r) {
    const w = r.wcmd;
    if (!w || typeof w.x !== "number" || typeof w.y !== "number") return null;
    if (Math.hypot(w.x - r.x, w.y - r.y) < this.intentMinM) return null;
    const g = this._arrow(r.x, r.y, w.x, w.y, this.intentColor, {
      cls: "live-intent", width: 3, dash: null, opacity: 0.9,
    });
    const tp = this.court.pxFromM(w.x, w.y);
    const dot = document.createElementNS(SVGNS, "circle");
    dot.setAttribute("cx", tp.sx);
    dot.setAttribute("cy", tp.sy);
    dot.setAttribute("r", "4");
    dot.setAttribute("fill", "none");
    dot.setAttribute("stroke", this.intentColor);
    dot.setAttribute("stroke-width", "2");
    g.appendChild(dot);
    return g;
  }

  _arrow(x1, y1, x2, y2, color, opts) {
    const o = opts || {};
    const a = this.court.pxFromM(x1, y1);
    const b = this.court.pxFromM(x2, y2);
    const g = document.createElementNS(SVGNS, "g");
    g.setAttribute("class", o.cls || "live-arrow");
    if (o.opacity != null) g.setAttribute("opacity", String(o.opacity));

    const line = document.createElementNS(SVGNS, "line");
    line.setAttribute("x1", a.sx);
    line.setAttribute("y1", a.sy);
    line.setAttribute("x2", b.sx);
    line.setAttribute("y2", b.sy);
    line.setAttribute("stroke", color);
    line.setAttribute("stroke-width", String(o.width || 2.5));
    line.setAttribute("stroke-linecap", "round");
    if (o.dash) line.setAttribute("stroke-dasharray", o.dash);
    g.appendChild(line);

    const ang = Math.atan2(b.sy - a.sy, b.sx - a.sx);
    const h = o.head || 9;  
    const spread = 0.42; 
    const p1x = b.sx - h * Math.cos(ang - spread);
    const p1y = b.sy - h * Math.sin(ang - spread);
    const p2x = b.sx - h * Math.cos(ang + spread);
    const p2y = b.sy - h * Math.sin(ang + spread);
    const head = document.createElementNS(SVGNS, "polygon");
    head.setAttribute("points", `${b.sx},${b.sy} ${p1x},${p1y} ${p2x},${p2y}`);
    head.setAttribute("fill", color);
    g.appendChild(head);
    return g;
  }

  // ─── markers ────────────────────────────────────────────────
  _robotMarker(r) {
    const court = this.court;
    const p = court.pxFromM(r.x, r.y);
    const color = colorForRobot(r.id);
    const faded = typeof r.age === "number" && r.age > this.fadeAge;

    const wrap = document.createElementNS(SVGNS, "g");
    wrap.setAttribute("class", "live-robot");
    wrap.setAttribute("opacity", faded ? "0.45" : "1");

    // Body radius: roughly proportional to the real robot footprint (~0.2 m).
    const rPx = Math.max(7, court.px(0.22));

    // Heading arrow (theta = field yaw, 0 = +x). Compute endpoint in field coordinates first.
    const headLen = 0.45; // m
    const hx = r.x + Math.cos(r.theta || 0) * headLen;
    const hy = r.y + Math.sin(r.theta || 0) * headLen;
    const hp = court.pxFromM(hx, hy);
    const head = document.createElementNS(SVGNS, "line");
    head.setAttribute("x1", p.sx);
    head.setAttribute("y1", p.sy);
    head.setAttribute("x2", hp.sx);
    head.setAttribute("y2", hp.sy);
    head.setAttribute("stroke", color);
    head.setAttribute("stroke-width", "3");
    head.setAttribute("stroke-linecap", "round");
    wrap.appendChild(head);

    const body = document.createElementNS(SVGNS, "circle");
    body.setAttribute("cx", p.sx);
    body.setAttribute("cy", p.sy);
    body.setAttribute("r", rPx);
    body.setAttribute("fill", color);
    body.setAttribute("fill-opacity", "0.35");
    body.setAttribute("stroke", color);
    body.setAttribute("stroke-width", "2.5");
    wrap.appendChild(body);

    // Label: "robot1" plus coordinates
    const label = document.createElementNS(SVGNS, "text");
    label.setAttribute("x", p.sx);
    label.setAttribute("y", p.sy - rPx - 6);
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("class", "live-robot-label");
    label.setAttribute("fill", color);
    label.textContent = `${r.name || "robot" + r.id}`;
    wrap.appendChild(label);

    const coord = document.createElementNS(SVGNS, "text");
    coord.setAttribute("x", p.sx);
    coord.setAttribute("y", p.sy + rPx + 13);
    coord.setAttribute("text-anchor", "middle");
    coord.setAttribute("class", "live-robot-coord");
    coord.textContent = `(${r.x.toFixed(2)}, ${r.y.toFixed(2)})`;
    wrap.appendChild(coord);

    return wrap;
  }

  /**
   * Marker for a vision-detected opponent robot.
   * No heading information is available, so draw a red diamond without orientation.
   * If o.seen_by > 1, multiple robots saw it at once, so show that in the label.
   */
  _opponentMarker(o) {
    const court = this.court;
    const p = court.pxFromM(o.x, o.y);
    const color = this.opponentColor;
    const d = Math.max(7, court.px(0.22)); // Roughly the same size as our robot marker.

    const wrap = document.createElementNS(SVGNS, "g");
    wrap.setAttribute("class", "live-opponent");

    // Diamond (a 45-degree rotated square) to distinguish it from our circular robot marker.
    const diamond = document.createElementNS(SVGNS, "polygon");
    diamond.setAttribute(
      "points",
      `${p.sx},${p.sy - d} ${p.sx + d},${p.sy} ${p.sx},${p.sy + d} ${p.sx - d},${p.sy}`,
    );
    diamond.setAttribute("fill", color);
    diamond.setAttribute("fill-opacity", "0.30");
    diamond.setAttribute("stroke", color);
    diamond.setAttribute("stroke-width", "2.5");
    wrap.appendChild(diamond);

    const label = document.createElementNS(SVGNS, "text");
    label.setAttribute("x", p.sx);
    label.setAttribute("y", p.sy - d - 5);
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("class", "live-opponent-label");
    label.setAttribute("fill", color);
    label.textContent = o.seen_by > 1 ? `${t("lbl-opponent")} ×${o.seen_by}` : t("lbl-opponent");
    wrap.appendChild(label);

    return wrap;
  }

  /** Color for merged balls: more simultaneous observers means higher confidence. */
  _ballColor(seen) {
    if (seen >= 4) return this.ballColor4;
    if (seen === 3) return this.ballColor3;
    if (seen === 2) return this.ballColor2;
    return this.ballColor1; // Single observer.
  }

  _ballMarker(ball) {
    const court = this.court;
    const p = court.pxFromM(ball.x, ball.y);
    const faded = typeof ball.age === "number" && ball.age > this.fadeAge;
    const rPx = Math.max(7, court.px(0.11)); // Ball radius ~0.11 m.
    const seen = ball.seen_by || 1;
    // If a single robot saw the ball, use that robot's color.
    // If multiple robots contributed to a merged ball (no single source), use the seen_by scale.
    const color = ball.source != null ? colorForRobot(ball.source) : this._ballColor(seen);

    const wrap = document.createElementNS(SVGNS, "g");
    wrap.setAttribute("class", "live-ball");
    wrap.setAttribute("opacity", faded ? "0.45" : "1");

    const border = document.createElementNS(SVGNS, "circle");
    border.setAttribute("cx", p.sx);
    border.setAttribute("cy", p.sy);
    border.setAttribute("r", rPx + 2);
    border.setAttribute("fill", "none");
    border.setAttribute("stroke", color);
    border.setAttribute("stroke-width", "2.5");
    wrap.appendChild(border);

    const emoji = document.createElementNS(SVGNS, "text");
    emoji.setAttribute("x", p.sx);
    emoji.setAttribute("y", p.sy);
    emoji.setAttribute("text-anchor", "middle");
    emoji.setAttribute("dominant-baseline", "central");
    emoji.setAttribute("font-size", String(rPx * 2.2));
    emoji.textContent = "⚽";
    wrap.appendChild(emoji);

    const labelText = seen > 1 ? `×${seen}` : (
      ball.source_name || (ball.source ? "robot" + ball.source : "")
    );
    if (labelText) {
      const label = document.createElementNS(SVGNS, "text");
      label.setAttribute("x", p.sx);
      label.setAttribute("y", p.sy - rPx - 7);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("class", "live-ball-label");
      label.setAttribute("fill", color);
      label.textContent = labelText;
      wrap.appendChild(label);
    }

    return wrap;
  }

  // Per-robot fused overlay markers (image + halo ring)
  /** Magenta = fused with self included; yellow = visible only through teammates. */
  _selfColor(selfSeen) {
    return selfSeen ? this.selfSeenColor : this.teamSeenColor;
  }

  /** Shared image-marker helper: halo ring (ringColor) + centered PNG + label. */
  _imageMarker(xm, ym, href, sizePx, ringColor, opts) {
    const o = opts || {};
    const p = this.court.pxFromM(xm, ym);
    const wrap = document.createElementNS(SVGNS, "g");
    wrap.setAttribute("class", o.cls || "live-fused");
    if (o.opacity != null) wrap.setAttribute("opacity", String(o.opacity));

    // Halo ring for self-seen / teammate-seen state, or the robot color.
    const ring = document.createElementNS(SVGNS, "circle");
    ring.setAttribute("cx", p.sx);
    ring.setAttribute("cy", p.sy);
    ring.setAttribute("r", sizePx * 0.6 + 2);
    ring.setAttribute("fill", "none");
    ring.setAttribute("stroke", ringColor);
    ring.setAttribute("stroke-width", "3");
    ring.setAttribute("stroke-opacity", "0.95");
    wrap.appendChild(ring);

    // Centered marker PNG. Set both SVG2 href and legacy xlink:href for compatibility.
    const img = document.createElementNS(SVGNS, "image");
    img.setAttribute("x", p.sx - sizePx / 2);
    img.setAttribute("y", p.sy - sizePx / 2);
    img.setAttribute("width", sizePx);
    img.setAttribute("height", sizePx);
    img.setAttribute("href", href);
    img.setAttributeNS(XLINKNS, "xlink:href", href);
    img.setAttribute("preserveAspectRatio", "xMidYMid meet");
    wrap.appendChild(img);

    if (o.label) {
      const label = document.createElementNS(SVGNS, "text");
      label.setAttribute("x", p.sx);
      label.setAttribute("y", p.sy - sizePx / 2 - 5);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("class", "live-fused-label");
      label.setAttribute("fill", ringColor);
      label.textContent = o.label;
      wrap.appendChild(label);
    }
    return wrap;
  }

  _ballSizePx() { return Math.max(16, this.court.px(0.26)); }
  _enemySizePx() { return Math.max(18, this.court.px(0.30)); }

  /** Ball seen directly by this robot (raw ball_pos), marked with a robot-color ring. */
  _ownBallMarker(r) {
    const bp = r.ball_pos;
    return this._imageMarker(bp.x, bp.y, BALL_IMG, this._ballSizePx(),
      colorForRobot(r.id), { cls: "live-own-ball", label: `R${r.id} ${t("lbl-ball")}` });
  }

  /** Fused ball: magenta=self included/direct, yellow=teammate-only. CI=num_sources. */
  _fusedBallMarker(r) {
    const fb = r.fused_ball;
    const ci = fb.num_sources ? ` CI:${fb.num_sources}` : "";
    return this._imageMarker(fb.x, fb.y, BALL_IMG, this._ballSizePx(),
      this._selfColor(fb.self_seen), { cls: "live-fused-ball", label: `R${r.id} ${t("lbl-fused-ball")}${ci}` });
  }

  /** Fused enemy: devil image + magenta=self included/direct, yellow=teammate-only. */
  _fusedEnemyMarker(r, en) {
    const ci = en.num_sources ? ` CI:${en.num_sources}` : "";
    return this._imageMarker(en.x, en.y, ENEMY_IMG, this._enemySizePx(),
      this._selfColor(en.self_seen), { cls: "live-fused-enemy", label: `R${r.id} ${t("lbl-fused-enemy")}${ci}` });
  }
}
