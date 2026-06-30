export class Court {
  constructor(svgEl, fieldCfg) {
    this.svg = svgEl;
    this.field = fieldCfg;
    this.padding = 30; // px
    this.fitFraction = 0.78; // Use only this fraction of the available area for the court.
    this._view = null;      // Current viewBox {x,y,w,h} (zoom/pan state)
    this._baseView = null;  // Fit-based viewBox (= 1x zoom)
    this._fit();
    window.addEventListener("resize", () => this._fit());
    this._enableZoomPan();
  }

  _fit() {
    const rect = this.svg.getBoundingClientRect();
    const innerW = rect.width - this.padding * 2;
    const innerH = rect.height - this.padding * 2;
    if (innerW <= 0 || innerH <= 0) return;
    // Preserve the court aspect ratio.
    const ratio = this.field.length_m / this.field.width_m;
    let w = innerW;
    let h = innerW / ratio;
    if (h > innerH) {
      h = innerH;
      w = innerH * ratio;
    }
    // Use only fitFraction of the available area to keep extra margin around the court.
    w *= this.fitFraction;
    h *= this.fitFraction;
    this.scale = w / this.field.length_m; // px per meter
    this.padX = (rect.width - w) / 2;
    this.padY = (rect.height - h) / 2;
    this.svgWidth = rect.width;
    this.svgHeight = rect.height;
    // Reset zoom/pan to the fit view on resize.
    this._baseView = { x: 0, y: 0, w: rect.width, h: rect.height };
    this._view = { ...this._baseView };
    this._applyView();
    this._render();
    if (this._onResize) this._onResize();
  }

  onResize(cb) { this._onResize = cb; }

  _applyView() {
    const v = this._view || this._baseView;
    if (v) this.svg.setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`);
  }

  /** Reset zoom/pan back to the fit (1x) view. */
  resetView() {
    if (!this._baseView) return;
    this._view = { ...this._baseView };
    this._applyView();
  }

  /** Convert screen-space px to internal SVG coordinates with zoom/pan applied. */
  clientToInternal(clientX, clientY) {
    if (this.svg.getScreenCTM && typeof this.svg.createSVGPoint === "function") {
      const ctm = this.svg.getScreenCTM();
      if (ctm) {
        const pt = this.svg.createSVGPoint();
        pt.x = clientX; pt.y = clientY;
        const p = pt.matrixTransform(ctm.inverse());
        return { x: p.x, y: p.y };
      }
    }
    // Fallback: map proportionally within the current viewBox.
    const rect = this.svg.getBoundingClientRect();
    const v = this._view || { x: 0, y: 0, w: rect.width, h: rect.height };
    return {
      x: v.x + (clientX - rect.left) / rect.width * v.w,
      y: v.y + (clientY - rect.top) / rect.height * v.h,
    };
  }

  /** Convert screen-space px to field coordinates (m) with zoom/pan applied. */
  mFromClient(clientX, clientY) {
    const p = this.clientToInternal(clientX, clientY);
    return this.mFromPx(p.x, p.y);
  }

  /** Wheel zoom, middle-button pan, and double-click reset via viewBox only. */
  _enableZoomPan() {
    const svg = this.svg;

    svg.addEventListener("wheel", (e) => {
      if (!this._view || !this._baseView) return;
      e.preventDefault();
      const factor = e.deltaY < 0 ? 0.85 : 1 / 0.85; // Zoom in when scrolling upward.
      this._zoomAt(e.clientX, e.clientY, factor);
    }, { passive: false });

    let panning = false, lastX = 0, lastY = 0;
    svg.addEventListener("mousedown", (e) => {
      if (e.button !== 1) return; // Only pan with the middle button.
      e.preventDefault();
      e.stopImmediatePropagation(); // Block other handlers such as empty-space deselect.
      panning = true; lastX = e.clientX; lastY = e.clientY;
    });
    window.addEventListener("mousemove", (e) => {
      if (!panning || !this._view) return;
      const rect = svg.getBoundingClientRect();
      this._view.x -= (e.clientX - lastX) / rect.width * this._view.w;
      this._view.y -= (e.clientY - lastY) / rect.height * this._view.h;
      this._clampView();
      lastX = e.clientX; lastY = e.clientY;
      this._applyView();
    });
    window.addEventListener("mouseup", (e) => { if (e.button === 1) panning = false; });

    svg.addEventListener("dblclick", () => this.resetView());
  }

  _zoomAt(clientX, clientY, factor) {
    const base = this._baseView, v = this._view;
    const minW = base.w / 8; // Allow up to 8x zoom in.
    let newW = v.w * factor;
    let newH = v.h * factor;
    if (newW > base.w) { newW = base.w; newH = base.h; }   // Do not zoom out beyond fit.
    if (newW < minW)   { newW = minW;  newH = base.h * (minW / base.w); }
    const rect = this.svg.getBoundingClientRect();
    const fx = (clientX - rect.left) / rect.width;
    const fy = (clientY - rect.top) / rect.height;
    const curX = v.x + fx * v.w;   // Internal coordinate under the cursor (anchor point)
    const curY = v.y + fy * v.h;
    this._view = { x: curX - fx * newW, y: curY - fy * newH, w: newW, h: newH };
    this._clampView();
    this._applyView();
  }

  /** Clamp the view so it never escapes the base fit area. */
  _clampView() {
    const base = this._baseView, v = this._view;
    if (!base) return;
    v.x = Math.max(base.x, Math.min(v.x, base.x + base.w - v.w));
    v.y = Math.max(base.y, Math.min(v.y, base.y + base.h - v.h));
  }

  /** Tint the inside of the court with a subtle hint color based on the default action.
   *  Design ref: Section B visualization; alpha ~= 0.10 and gray when no action is set.
   *  Inserted at the front of the SVG, so it renders behind court-lines / zones-group.
   */
  setBgHint(action) {
    const colorMap = {
      dribble: "rgba(46, 204, 113, 0.12)",
      kick:    "rgba(231, 76, 60, 0.12)",
      pass:    "rgba(52, 152, 219, 0.12)",
      move_to: "rgba(241, 196, 15, 0.12)",
      turn_to: "rgba(155, 89, 182, 0.12)",
      none:    "rgba(127, 127, 127, 0.06)",
    };
    const fill = colorMap[action] || colorMap.none;

    const existing = this.svg.querySelector("#court-bg-hint");
    if (existing) existing.remove();

    const f = this.field;
    const tl = this.pxFromM(-f.length_m / 2, f.width_m / 2);
    const br = this.pxFromM(f.length_m / 2, -f.width_m / 2);
    const r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    r.setAttribute("id", "court-bg-hint");
    r.setAttribute("class", "court-bg-hint");
    r.setAttribute("x", tl.sx);
    r.setAttribute("y", tl.sy);
    r.setAttribute("width", br.sx - tl.sx);
    r.setAttribute("height", br.sy - tl.sy);
    r.setAttribute("fill", fill);

    if (this.svg.firstChild) this.svg.insertBefore(r, this.svg.firstChild);
    else this.svg.appendChild(r);
  }

  pxFromM(x, y) {
    const L = this.field.length_m;
    const W = this.field.width_m;
    return {
      sx: (x + L / 2) * this.scale + this.padX,
      sy: (W / 2 - y) * this.scale + this.padY,
    };
  }

  mFromPx(sx, sy) {
    const L = this.field.length_m;
    const W = this.field.width_m;
    return {
      x: (sx - this.padX) / this.scale - L / 2,
      y: W / 2 - (sy - this.padY) / this.scale,
    };
  }

  // Length in meters to pixels (scale)
  px(m) { return m * this.scale; }

  _render() {
    // Update only the court-line group; do not touch zone groups added elsewhere.
    // Source: HSL-Rules/rules/medium_field.tex
    const existing = this.svg.querySelector("#court-lines");
    if (existing) existing.remove();
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("id", "court-lines");
    const f = this.field;
    const L = f.length_m, W = f.width_m;

    // Line width: m -> px, with a 1px minimum.
    const fieldLW = Math.max(1, this.px(f.line_width_m || 0.05));
    const goalLW  = Math.max(2, this.px(f.goal_line_width_m || 0.10));

    // 0) Border strip (safety area outside the field), shown faintly
    const bs = f.border_strip_m || 0;
    if (bs > 0) {
      const btl = this.pxFromM(-L / 2 - bs, W / 2 + bs);
      const bbr = this.pxFromM(L / 2 + bs, -W / 2 - bs);
      const borderRect = this._rect(btl.sx, btl.sy, bbr.sx - btl.sx, bbr.sy - btl.sy);
      borderRect.setAttribute("class", "");
      borderRect.setAttribute("fill", "rgba(255,255,255,0.05)");
      borderRect.setAttribute("stroke", "rgba(255,255,255,0.4)");
      borderRect.setAttribute("stroke-dasharray", "4 4");
      borderRect.setAttribute("stroke-width", "1");
      g.appendChild(borderRect);
    }

    // 1) Outer boundary (field lines)
    const tl = this.pxFromM(-L / 2, W / 2);
    const br = this.pxFromM(L / 2, -W / 2);
    const outer = this._rect(tl.sx, tl.sy, br.sx - tl.sx, br.sy - tl.sy);
    outer.setAttribute("stroke-width", fieldLW);
    g.appendChild(outer);

    // 2) Center line (halfway line)
    const t = this.pxFromM(0, W / 2);
    const b = this.pxFromM(0, -W / 2);
    const half = this._line(t.sx, t.sy, b.sx, b.sy);
    half.setAttribute("stroke-width", fieldLW);
    g.appendChild(half);

    // 3) Center circle (radius 1.5 m, diameter 3.0 m)
    const c = this.pxFromM(0, 0);
    const cc = this._circle(c.sx, c.sy, this.px(f.center_circle_r_m));
    cc.setAttribute("stroke-width", fieldLW);
    g.appendChild(cc);

    // 4) Center mark (same as the penalty mark; see LaTeX line 97)
    // Inline style overrides the #court .field-line { fill: none } CSS.
    const pmDia = f.penalty_mark_diameter_m || 0.1;
    const pmR_px = this.px(pmDia) / 2;
    const centerMark = this._circle(c.sx, c.sy, Math.max(2, pmR_px));
    centerMark.style.fill = "#fff";
    centerMark.style.stroke = "none";
    g.appendChild(centerMark);

    // 5) Left/right symmetric elements: goal area / penalty area / penalty mark / goal
    const ga = f.goal_area;
    const pa = f.penalty_area;
    const pmd = f.penalty_mark_distance_m;
    const goal = f.goal;

    for (const side of [-1, 1]) {
      // ── goal area (depth 1.0 × width 4.0)
      {
        const xIn = (L / 2 - ga.depth_m) * side;
        const xEdge = (L / 2) * side;
        const x1 = Math.min(xIn, xEdge), x2 = Math.max(xIn, xEdge);
        const tlg = this.pxFromM(x1, ga.width_m / 2);
        const brg = this.pxFromM(x2, -ga.width_m / 2);
        const r = this._rect(tlg.sx, tlg.sy, brg.sx - tlg.sx, brg.sy - tlg.sy);
        r.setAttribute("stroke-width", fieldLW);
        g.appendChild(r);
      }
      // ── penalty area (depth 3.0 × width 6.0)
      {
        const xIn = (L / 2 - pa.depth_m) * side;
        const xEdge = (L / 2) * side;
        const x1 = Math.min(xIn, xEdge), x2 = Math.max(xIn, xEdge);
        const tlp = this.pxFromM(x1, pa.width_m / 2);
        const brp = this.pxFromM(x2, -pa.width_m / 2);
        const r = this._rect(tlp.sx, tlp.sy, brp.sx - tlp.sx, brp.sy - tlp.sy);
        r.setAttribute("stroke-width", fieldLW);
        g.appendChild(r);
      }
      // -- penalty mark (distance 2.0 m from the goal line -> x = +/-5.0)
      // Inline style overrides the .field-line { fill: none } CSS.
      {
        const pmX = (L / 2 - pmd) * side;
        const pm = this.pxFromM(pmX, 0);
        const dot = this._circle(pm.sx, pm.sy, Math.max(2, pmR_px));
        dot.style.fill = "#fff";
        dot.style.stroke = "none";
        g.appendChild(dot);
      }
      // -- goal (depth 0.7 outside the field, inner width 2.4) at goalLineWidth(0.10)
      {
        const post = goal.inner_width_m / 2;       // ±1.2
        const xOut = (L / 2 + goal.depth_m) * side;
        const xIn = (L / 2) * side;
        const gx1 = Math.min(xOut, xIn), gx2 = Math.max(xOut, xIn);
        const tlGoal = this.pxFromM(gx1, post);
        const brGoal = this.pxFromM(gx2, -post);
        const net = this._rect(tlGoal.sx, tlGoal.sy, brGoal.sx - tlGoal.sx, brGoal.sy - tlGoal.sy);
        net.setAttribute("stroke", "#ffeb3b");
        net.setAttribute("stroke-width", goalLW);
        net.setAttribute("fill", "rgba(255,235,59,0.15)");
        g.appendChild(net);
      }
    }

    // 6) Corner arcs (radius 0.5 m, 90 degrees inward from each corner)
    // dx/dy indicate the inward direction in SVG coordinates. Because pxFromM flips y,
    // +y inward in field coordinates becomes -y in SVG.
    //   BL SVG bottom-left: inward = +x_svg, -y_svg
    //   BR SVG bottom-right: inward = -x_svg, -y_svg
    //   TR SVG top-right: inward = -x_svg, +y_svg
    //   TL SVG top-left: inward = +x_svg, +y_svg
    const ar = f.corner_arc_radius_m || 0.5;
    const arPx = this.px(ar);
    const corners = [
      { x: -L / 2, y: -W / 2, dx:  1, dy: -1 }, // BL field -> SVG bottom-left
      { x:  L / 2, y: -W / 2, dx: -1, dy: -1 }, // BR field -> SVG bottom-right
      { x:  L / 2, y:  W / 2, dx: -1, dy:  1 }, // TR field -> SVG top-right
      { x: -L / 2, y:  W / 2, dx:  1, dy:  1 }, // TL field -> SVG top-left
    ];
    for (const cr of corners) {
      const p = this.pxFromM(cr.x, cr.y);
      const x1 = p.sx + cr.dx * arPx;            // Endpoint along the x axis
      const y1 = p.sy;
      const x2 = p.sx;
      const y2 = p.sy + cr.dy * arPx;            // Endpoint along the y axis
      // SVG arc: M(x1,y1) A r r 0 large-arc=0 sweep x2 y2
      // SVG sweep: 1=clockwise (SVG coordinates), 0=counter-clockwise
      // dx*dy>0 (same sign) -> CW -> sweep=1, dx*dy<0 (different sign) -> CCW -> sweep=0
      const sweep = (cr.dx * cr.dy) > 0 ? 1 : 0;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute(
        "d",
        `M ${x1} ${y1} A ${arPx} ${arPx} 0 0 ${sweep} ${x2} ${y2}`,
      );
      path.setAttribute("class", "field-line");
      path.setAttribute("stroke-width", fieldLW);
      path.setAttribute("fill", "none");
      g.appendChild(path);
    }

    // Place court lines behind the zone group.
    // setBgHint inserts #court-bg-hint as svg.firstChild, so place this right after it.
    const bgHint = this.svg.querySelector("#court-bg-hint");
    if (bgHint && bgHint.nextSibling) {
      this.svg.insertBefore(g, bgHint.nextSibling);
    } else if (this.svg.firstChild) {
      this.svg.insertBefore(g, this.svg.firstChild);
    } else {
      this.svg.appendChild(g);
    }
  }

  // ─── SVG helpers ────────────────────────────────────────────────
  _rect(x, y, w, h) {
    const r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    r.setAttribute("x", x); r.setAttribute("y", y);
    r.setAttribute("width", w); r.setAttribute("height", h);
    r.setAttribute("class", "field-line");
    return r;
  }
  _line(x1, y1, x2, y2) {
    const l = document.createElementNS("http://www.w3.org/2000/svg", "line");
    l.setAttribute("x1", x1); l.setAttribute("y1", y1);
    l.setAttribute("x2", x2); l.setAttribute("y2", y2);
    l.setAttribute("class", "field-line");
    return l;
  }
  _circle(cx, cy, r) {
    const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", cx); c.setAttribute("cy", cy); c.setAttribute("r", r);
    c.setAttribute("class", "field-line");
    return c;
  }
  _text(x, y, t) {
    const e = document.createElementNS("http://www.w3.org/2000/svg", "text");
    e.setAttribute("x", x); e.setAttribute("y", y);
    e.textContent = t;
    return e;
  }
}
