import { t } from "./i18n.js";

const SVG_NS = "http://www.w3.org/2000/svg";

export class ZoneLayer {
  constructor(svgEl, court, store) {
    this.svg = svgEl;
    this.court = court;
    this.store = store;
    this.group = null;
    this._dragState = null;
    this._ensureGroup();

    this.svg.addEventListener("mousemove", (e) => this._onMouseMove(e));
    this.svg.addEventListener("mouseup", () => this._onMouseUp());
    this.svg.addEventListener("mouseleave", () => this._onMouseUp());
  }

  _ensureGroup() {
    let g = this.svg.querySelector("#zones-group");
    if (!g) {
      g = document.createElementNS(SVG_NS, "g");
      g.setAttribute("id", "zones-group");
      this.svg.appendChild(g);
    }
    this.group = g;
  }

  render() {
    this._ensureGroup();
    this.group.innerHTML = "";
    // 1) All zone shapes + labels + handles for the selected zone
    for (const z of this.store.zones) {
      this._renderZone(z, this.store.isHidden && this.store.isHidden(z.id));
    }
    // 2) Draw every zone's target marker above its shape so it never gets hidden.
    //    Handles are still rendered per zone inside _renderZone, but interactions
    //    such as alt+click cycling bypass the markers, so the markers do not block them.
    for (const z of this.store.zones) {
      if (this.store.isHidden && this.store.isHidden(z.id)) continue;
      this._renderTargetMarker(z);
    }
  }

  /** Alt+click cycle entry point, called from app.js on SVG mousedown. */
  cycleSelectAt(fieldX, fieldY) {
    const hits = this._hitsAt(fieldX, fieldY);
    if (hits.length === 0) return null;
    const currentIdx = hits.findIndex((z) => z.id === this.store.selectedId);
    // Cycle starting from the visually topmost zone (end of the YAML array).
    // hits follows YAML order, so walk backward from the end.
    const nextIdx = currentIdx < 0
      ? hits.length - 1
      : (currentIdx - 1 + hits.length) % hits.length;
    const nextId = hits[nextIdx].id;
    if (this.store.selectZone) this.store.selectZone(nextId);
    return nextId;
  }

  /** Visible zones containing the given coordinate, in YAML array order. */
  _hitsAt(x, y) {
    const out = [];
    for (const z of this.store.zones) {
      if (this.store.isHidden && this.store.isHidden(z.id)) continue;
      if (this._contains(z, x, y)) out.push(z);
    }
    return out;
  }

  _contains(z, x, y) {
    if (z.type === "rect") {
      const x1 = Math.min(z.geometry.x1, z.geometry.x2);
      const x2 = Math.max(z.geometry.x1, z.geometry.x2);
      const y1 = Math.min(z.geometry.y1, z.geometry.y2);
      const y2 = Math.max(z.geometry.y1, z.geometry.y2);
      return x >= x1 && x <= x2 && y >= y1 && y <= y2;
    }
    if (z.type === "circle") {
      const dx = x - z.geometry.cx;
      const dy = y - z.geometry.cy;
      return Math.hypot(dx, dy) <= z.geometry.r;
    }
    return false;
  }

  _renderZone(z, hidden) {
    const isSel = z.id === this.store.selectedId;
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("data-zone-id", z.id);

    if (z.type === "rect") {
      const tl = this.court.pxFromM(
        Math.min(z.geometry.x1, z.geometry.x2),
        Math.max(z.geometry.y1, z.geometry.y2),
      );
      const br = this.court.pxFromM(
        Math.max(z.geometry.x1, z.geometry.x2),
        Math.min(z.geometry.y1, z.geometry.y2),
      );
      const w = br.sx - tl.sx;
      const h = br.sy - tl.sy;

      const r = document.createElementNS(SVG_NS, "rect");
      r.setAttribute("x", tl.sx);
      r.setAttribute("y", tl.sy);
      r.setAttribute("width", w);
      r.setAttribute("height", h);
      r.setAttribute("fill", z.color);
      r.setAttribute("stroke", z.color);
      r.setAttribute(
        "class",
        "zone-shape" + (isSel ? " selected" : "") + (hidden ? " hidden-zone" : ""),
      );
      r.addEventListener("mousedown", (e) => this._startDrag(e, z, "move"));
      g.appendChild(r);

      const label = document.createElementNS(SVG_NS, "text");
      label.setAttribute("x", tl.sx + 6);
      label.setAttribute("y", tl.sy + 14);
      label.setAttribute("class", "zone-label" + (hidden ? " hidden-zone" : ""));
      label.textContent = z.name || z.id;
      g.appendChild(label);

      if (isSel && !hidden) {
        const handles = [
          { id: "nw", sx: tl.sx, sy: tl.sy, cls: "" },
          { id: "ne", sx: br.sx, sy: tl.sy, cls: "" },
          { id: "se", sx: br.sx, sy: br.sy, cls: "" },
          { id: "sw", sx: tl.sx, sy: br.sy, cls: "" },
          { id: "n",  sx: (tl.sx + br.sx) / 2, sy: tl.sy, cls: "n" },
          { id: "s",  sx: (tl.sx + br.sx) / 2, sy: br.sy, cls: "s" },
          { id: "e",  sx: br.sx, sy: (tl.sy + br.sy) / 2, cls: "e" },
          { id: "w",  sx: tl.sx, sy: (tl.sy + br.sy) / 2, cls: "w" },
        ];
        for (const h of handles) {
          const c = document.createElementNS(SVG_NS, "rect");
          c.setAttribute("x", h.sx - 5);
          c.setAttribute("y", h.sy - 5);
          c.setAttribute("width", 10);
          c.setAttribute("height", 10);
          c.setAttribute("class", "zone-handle " + h.cls);
          c.addEventListener("mousedown", (e) => this._startDrag(e, z, "resize:" + h.id));
          g.appendChild(c);
        }
      }
    } else if (z.type === "circle") {
      const c = this.court.pxFromM(z.geometry.cx, z.geometry.cy);
      const rPx = this.court.px(z.geometry.r);

      const circ = document.createElementNS(SVG_NS, "circle");
      circ.setAttribute("cx", c.sx);
      circ.setAttribute("cy", c.sy);
      circ.setAttribute("r", rPx);
      circ.setAttribute("fill", z.color);
      circ.setAttribute("stroke", z.color);
      circ.setAttribute(
        "class",
        "zone-shape" + (isSel ? " selected" : "") + (hidden ? " hidden-zone" : ""),
      );
      circ.addEventListener("mousedown", (e) => this._startDrag(e, z, "move"));
      g.appendChild(circ);

      const label = document.createElementNS(SVG_NS, "text");
      label.setAttribute("x", c.sx);
      label.setAttribute("y", c.sy);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("class", "zone-label" + (hidden ? " hidden-zone" : ""));
      label.textContent = z.name || z.id;
      g.appendChild(label);

      if (isSel && !hidden) {
        const hx = c.sx + rPx;
        const hy = c.sy;
        const handle = document.createElementNS(SVG_NS, "rect");
        handle.setAttribute("x", hx - 5);
        handle.setAttribute("y", hy - 5);
        handle.setAttribute("width", 10);
        handle.setAttribute("height", 10);
        handle.setAttribute("class", "zone-handle circle-r");
        handle.addEventListener("mousedown", (e) => this._startDrag(e, z, "resize:r"));
        g.appendChild(handle);
      }
    }

    this.group.appendChild(g);
  }

  _startDrag(evt, zone, mode) {
    // Alt/Shift+click does not start dragging; app.js handles cycling instead.
    if (evt.altKey || evt.shiftKey) return;
    // Hidden zones block all interaction.
    if (this.store.isHidden && this.store.isHidden(zone.id)) return;
    evt.stopPropagation();
    evt.preventDefault();
    if (this.store.selectZone) this.store.selectZone(zone.id);
    const pt = this._mouseM(evt);
    this._dragState = {
      zone,
      mode,
      startM: pt,
      orig: JSON.parse(JSON.stringify(zone.geometry)),
    };
    this.render();
  }

  _onMouseMove(evt) {
    const pt = this._mouseM(evt);
    if (this.store.onCursor) this.store.onCursor(pt);
    if (!this._dragState) return;
    const { zone, mode, startM, orig } = this._dragState;
    const dx = pt.x - startM.x;
    const dy = pt.y - startM.y;

    if (zone.type === "rect") {
      const x1o = Math.min(orig.x1, orig.x2);
      const x2o = Math.max(orig.x1, orig.x2);
      const y1o = Math.min(orig.y1, orig.y2);
      const y2o = Math.max(orig.y1, orig.y2);
      let nx1 = x1o, nx2 = x2o, ny1 = y1o, ny2 = y2o;

      if (mode === "move") {
        nx1 += dx; nx2 += dx; ny1 += dy; ny2 += dy;
      } else if (mode.startsWith("resize:")) {
        const h = mode.split(":")[1];
        if (h.includes("w")) nx1 = x1o + dx;
        if (h.includes("e")) nx2 = x2o + dx;
        if (h.includes("n")) ny2 = y2o + dy;
        if (h.includes("s")) ny1 = y1o + dy;
      }
      if (Math.abs(nx2 - nx1) < 0.1) nx2 = nx1 + 0.1;
      if (Math.abs(ny2 - ny1) < 0.1) ny2 = ny1 + 0.1;
      zone.geometry.x1 = round3(nx1);
      zone.geometry.y1 = round3(ny1);
      zone.geometry.x2 = round3(nx2);
      zone.geometry.y2 = round3(ny2);
    } else if (zone.type === "circle") {
      if (mode === "move") {
        zone.geometry.cx = round3(orig.cx + dx);
        zone.geometry.cy = round3(orig.cy + dy);
      } else if (mode === "resize:r") {
        const distM = Math.hypot(pt.x - orig.cx, pt.y - orig.cy);
        zone.geometry.r = round3(Math.max(0.1, distM));
      }
    }
    this.render();
    if (this.store.onMutate) this.store.onMutate(zone);
  }

  _onMouseUp() {
    if (this._dragState && this.store.onMutate) {
      this.store.onMutate(this._dragState.zone);
    }
    this._dragState = null;
  }

  _mouseM(evt) {
    // mFromClient applies inverse-CTM conversion with the current zoom/pan viewBox.
    return this.court.mFromClient(evt.clientX, evt.clientY);
  }

  // ─── Target Marker ────────────────────────────────────────────────
  // Design ref: target markers visualize action_policy.xy on the court.
  //   Conditions: space=global, action != none, xy parses successfully, zone is visible.
  //   Selected-zone markers connect zone center -> marker with a dashed line and thicker stroke.

  _zoneCenterM(z) {
    if (z.type === "rect") {
      return {
        x: (Number(z.geometry.x1) + Number(z.geometry.x2)) / 2,
        y: (Number(z.geometry.y1) + Number(z.geometry.y2)) / 2,
      };
    }
    if (z.type === "circle") {
      return { x: Number(z.geometry.cx), y: Number(z.geometry.cy) };
    }
    return null;
  }

  _renderTargetMarker(z) {
    // 1) Visibility guard
    if (!z || z.space !== "global") return;
    const ap = z.action_policy || {};
    if (!ap.action || ap.action === "none") return;
    const pt = parseXY(ap.xy, z.id);
    if (!pt) return;

    const isSel = z.id === this.store.selectedId;
    const color = z.color || "#3498db";
    const center = this.court.pxFromM(pt.x, pt.y);

    // 2) Marker size: 0.25 m radius, minimum 8 px
    const rPx = Math.max(8, this.court.px(0.25));

    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", "zone-target-marker" + (isSel ? " selected" : ""));
    g.setAttribute("data-target-for", z.id);

    // 3) For the selected zone only, connect center -> marker with a dashed line
    if (isSel) {
      const c = this._zoneCenterM(z);
      if (c) {
        const cpx = this.court.pxFromM(c.x, c.y);
        const link = document.createElementNS(SVG_NS, "line");
        link.setAttribute("class", "zone-target-link");
        link.setAttribute("x1", cpx.sx);
        link.setAttribute("y1", cpx.sy);
        link.setAttribute("x2", center.sx);
        link.setAttribute("y2", center.sy);
        link.setAttribute("stroke", color);
        g.appendChild(link);
      }
    }

    // 4) Outer ring (semi-transparent fill, stronger stroke in the zone color)
    const ring = document.createElementNS(SVG_NS, "circle");
    ring.setAttribute("class", "zone-target-ring");
    ring.setAttribute("cx", center.sx);
    ring.setAttribute("cy", center.sy);
    ring.setAttribute("r", rPx);
    ring.setAttribute("fill", color);
    ring.setAttribute("fill-opacity", isSel ? "0.35" : "0.20");
    ring.setAttribute("stroke", color);
    ring.setAttribute("stroke-width", isSel ? 3 : 2);
    g.appendChild(ring);

    // 5) Inner cross (+), 70% of the outer ring radius
    const armPx = rPx * 0.7;
    const hLine = document.createElementNS(SVG_NS, "line");
    hLine.setAttribute("class", "zone-target-cross");
    hLine.setAttribute("x1", center.sx - armPx);
    hLine.setAttribute("y1", center.sy);
    hLine.setAttribute("x2", center.sx + armPx);
    hLine.setAttribute("y2", center.sy);
    hLine.setAttribute("stroke", color);
    g.appendChild(hLine);

    const vLine = document.createElementNS(SVG_NS, "line");
    vLine.setAttribute("class", "zone-target-cross");
    vLine.setAttribute("x1", center.sx);
    vLine.setAttribute("y1", center.sy - armPx);
    vLine.setAttribute("x2", center.sx);
    vLine.setAttribute("y2", center.sy + armPx);
    vLine.setAttribute("stroke", color);
    g.appendChild(vLine);

    // 6) Tooltip via SVG <title> (native hover)
    const title = document.createElementNS(SVG_NS, "title");
    const targetStr = ap.target ? ` → ${ap.target}` : "";
    title.textContent =
      `${z.name || z.id}\n` +
      `action: ${ap.action}${targetStr}\n` +
      `xy: ${ap.xy}  (${t("field-coord-label")} x=${pt.x.toFixed(2)}, y=${pt.y.toFixed(2)})`;
    g.appendChild(title);

    // 7) Click to select this zone
    g.addEventListener("mousedown", (e) => {
      // Delegate alt+click to the court-level cycle handler, same as zone shapes do.
      if (e.altKey || e.shiftKey) return;
      e.stopPropagation();
      e.preventDefault();
      if (this.store.selectZone) this.store.selectZone(z.id);
    });
    g.style.cursor = "pointer";

    this.group.appendChild(g);
  }
}

/**
 * Parse an "x;y" or "x;y;z" string into {x, y}. Ignore z.
 * Return null on failure and console.warn for a silent skip.
 */
function parseXY(raw, zoneId) {
  if (raw == null) return null;
  if (typeof raw !== "string") return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const parts = trimmed.split(";");
  if (parts.length < 2) {
    console.warn(`[zones] parseXY: '${raw}' 형식 오류 (zone='${zoneId}')`);
    return null;
  }
  const x = parseFloat(parts[0]);
  const y = parseFloat(parts[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    console.warn(`[zones] parseXY: '${raw}' 숫자 변환 실패 (zone='${zoneId}')`);
    return null;
  }
  return { x, y };
}

function round3(v) { return Math.round(v * 1000) / 1000; }
