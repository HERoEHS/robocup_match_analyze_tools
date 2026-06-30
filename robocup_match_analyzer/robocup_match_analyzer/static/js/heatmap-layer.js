const SVGNS = 'http://www.w3.org/2000/svg';
const BINS_X = 28, BINS_Y = 18;
const FIELD_L = 14.0, FIELD_W = 9.0;

export class HeatmapLayer {
  // robotColorFn(rid) → CSS color string (e.g. '#60a5fa')
  constructor(court, robotColorFn) {
    this._court = court;
    this._colorFn = robotColorFn || (() => '#ffffff');
    this._data = null;
  }

  setData(data) {
    this._data = data;
  }

  clear() {
    const g = this._group();
    if (g) g.innerHTML = '';
  }

  // Full time-range render
  render(mode, playerIds, minT, maxT) {
    if (!this._data) return;
    const g = this._group();
    if (!g) return;
    g.innerHTML = '';
    this._drawFull(g, mode, playerIds, minT, maxT);
  }

  // Progressive playback mode accumulates samples from start until current time.
  renderProgressive(mode, playerIds, currentT) {
    this.render(mode, playerIds, 0, currentT);
  }

  // ── Private ─────────────────────────────────────────────────────────────────

  _group() {
    return this._court._svg.getElementById('g-heatmap2');
  }

  _drawFull(g, mode, playerIds, minT, maxT) {
    if (mode === 'ball') {
      const { grid, maxCount } = this._buildGrid(this._data.balls || [], minT, maxT);
      this._paintGrid(g, grid, maxCount, null);
    } else {
      for (const pid of playerIds) {
        const pts = mode === 'kick'
          ? (this._data.kicks?.[String(pid)] || [])
          : (this._data.robots?.[String(pid)] || []);
        const { grid, maxCount } = this._buildGrid(pts, minT, maxT);
        this._paintGrid(g, grid, maxCount, pid);
      }
    }
  }

  _buildGrid(pts, minT, maxT) {
    const grid = new Int32Array(BINS_X * BINS_Y);
    let maxCount = 0;
    for (const [t, x, y] of pts) {
      if (t < minT || t > maxT) continue;
      const ix = Math.floor((x + FIELD_L / 2) / FIELD_L * BINS_X);
      const iy = Math.floor((FIELD_W / 2 - y) / FIELD_W * BINS_Y);
      if (ix >= 0 && ix < BINS_X && iy >= 0 && iy < BINS_Y) {
        const slot = iy * BINS_X + ix;
        grid[slot]++;
        if (grid[slot] > maxCount) maxCount = grid[slot];
      }
    }
    return { grid, maxCount };
  }

  // robotId=null → ball color scheme; robotId=number → robot's own color
  _paintGrid(g, grid, maxCount, robotId) {
    if (!maxCount) return;
    const court = this._court;
    const cw = court._ts(FIELD_L / BINS_X) + 0.5;
    const ch = court._ts(FIELD_W / BINS_Y) + 0.5;
    const fill = robotId != null ? this._colorFn(robotId) : null;

    for (let iy = 0; iy < BINS_Y; iy++) {
      for (let ix = 0; ix < BINS_X; ix++) {
        const v = grid[iy * BINS_X + ix];
        if (!v) continue;
        const norm = v / maxCount;
        const xm = -FIELD_L / 2 + ix / BINS_X * FIELD_L;
        const ym =  FIELD_W / 2 - iy / BINS_Y * FIELD_W;
        const rect = document.createElementNS(SVGNS, 'rect');
        rect.setAttribute('x', court._tx(xm));
        rect.setAttribute('y', court._ty(ym));
        rect.setAttribute('width', cw);
        rect.setAttribute('height', ch);
        rect.setAttribute('fill', fill ?? this._ballColor(norm));
        rect.setAttribute('opacity', String(0.10 + norm * 0.67));
        g.appendChild(rect);
      }
    }
  }

  // Ball: Blue (240°) → Cyan (180°) — dense = cyan, sparse = blue
  _ballColor(norm) {
    return `hsl(${240 - norm * 60}, 90%, 55%)`;
  }
}
