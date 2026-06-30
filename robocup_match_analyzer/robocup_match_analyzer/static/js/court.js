export class CourtRenderer {
  constructor(svgEl) {
    this._svg = svgEl;
    this._cfg = null;
    this._scale = 1;
    this._ox = 0; this._oy = 0;
    this._robotColors = ['#60a5fa','#4ade80','#f59e0b','#a78bfa','#34d399'];
    this._enemyColors = ['#dc2626','#b91c1c','#ef4444','#991b1b','#f87171'];
    this._visibleRobots     = new Set();
    this._visiblePerception = new Set();
    this._visibleBasic      = new Set();
    this._visibleUdp        = new Set();
    this._showDest    = true;
    this._showTrail   = false;
    this._showBall    = true;
    this._showEnemies = true;
    this._showVoronoi = false;
    this._voronoiColorMode = 'individual';
    this._heatmapData = null;
    this._trailData = {};
    this._frame = null;
    this._lang = 'en';
    window.addEventListener('resize', () => this._resize());
  }

  init(cfg) { this._cfg = cfg; this._resize(); }

  setLang(lang)             { this._lang = lang; this._renderField(); this._render(); }
  setVisibleRobots(ids)     { this._visibleRobots = new Set(ids); this._render(); }
  setVisiblePerception(ids) { this._visiblePerception = new Set(ids); this._render(); }
  setVisibleBasic(ids)      { this._visibleBasic = new Set(ids); this._render(); }
  setVisibleUdp(ids)        { this._visibleUdp = new Set(ids); this._render(); }
  setShowDest(v)    { this._showDest = v;    this._render(); }
  setShowTrail(v)   { this._showTrail = v;   if (!v) this._trailData = {}; this._render(); }
  setShowBall(v)    { this._showBall = v;    this._render(); }
  setShowEnemies(v) { this._showEnemies = v; this._render(); }
  setShowVoronoi(v) { this._showVoronoi = v; this._render(); }
  setVoronoiColorMode(mode) {
    this._voronoiColorMode = mode === 'team' ? 'team' : 'individual';
    this._render();
  }
  setHeatmap(d)   { this._heatmapData = d; this._render(); }
  clearHeatmap()  { this._heatmapData = null; this._render(); }
  setTrail(d)     { this._trailData = d; this._render(); }
  clearTrail()    { this._trailData = {}; this._render(); }
  updateFrame(f)  { this._frame = f; this._render(); }
  analyzeSpaceControl(frame = this._frame, options = {}) {
    const { respectFilters = false, requireBothTeams = false } = options;
    if (!this._cfg || !frame) return null;

    const totalArea = this._fieldArea();
    const sites = this._collectVoronoiSites(frame, { respectFilters });
    if (sites.length < 2) {
      return {
        valid: false,
        totalArea,
        ourArea: 0,
        enemyArea: 0,
        ourPct: null,
        enemyPct: null,
        sites: [],
      };
    }

    const analyzedSites = [];
    let ourArea = 0;
    let enemyArea = 0;
    let ourCount = 0;
    let enemyCount = 0;

    for (const site of sites) {
      const cell = this._buildVoronoiCell(site, sites);
      if (cell.length < 3) continue;
      const area = this._polygonArea(cell);
      const pct = totalArea > 0 ? area / totalArea * 100 : 0;
      analyzedSites.push({ ...site, cell, area, pct });
      if (site.team === 'our') {
        ourArea += area;
        ourCount += 1;
      } else {
        enemyArea += area;
        enemyCount += 1;
      }
    }

    const valid = analyzedSites.length >= 2 && (
      !requireBothTeams || (ourCount > 0 && enemyCount > 0)
    );

    return {
      valid,
      totalArea,
      ourArea,
      enemyArea,
      ourPct: totalArea > 0 ? ourArea / totalArea * 100 : null,
      enemyPct: totalArea > 0 ? enemyArea / totalArea * 100 : null,
      sites: analyzedSites,
    };
  }

  robotColor(id) { return this._robotColors[(id - 1) % this._robotColors.length]; }
  enemyColor(idx) { return this._enemyColors[idx % this._enemyColors.length]; }

  onResize(cb) {
    if (!this._resizeCbs) this._resizeCbs = [];
    this._resizeCbs.push(cb);
  }

  // ── Coords ───────────────────────────────────────────────────────────
  _resize() {
    if (!this._svg.parentElement) return;
    const rect = this._svg.parentElement.getBoundingClientRect();
    const W = rect.width, H = rect.height;
    this._svg.setAttribute('width', W);
    this._svg.setAttribute('height', H);
    if (!this._cfg) return;
    const B = this._cfg.border_strip_m;
    const fw = this._cfg.length_m + B * 2;
    const fh = this._cfg.width_m  + B * 2;
    this._scale = Math.min(W / fw, H / fh) * 0.93;
    this._ox = W / 2;
    this._oy = H / 2;
    this._renderField();
    this._render();
    if (this._resizeCbs) this._resizeCbs.forEach(cb => cb());
  }

  _tx(x) { return this._ox + x * this._scale; }
  _ty(y) { return this._oy - y * this._scale; }
  _ts(m) { return m * this._scale; }

  _el(tag, attrs, parent) {
    const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    (parent || this._svg).appendChild(e);
    return e;
  }

  // ── Field ────────────────────────────────────────────────────────────
  _renderField() {
    if (!this._cfg) return;
    this._svg.innerHTML = '';
    const c = this._cfg;
    const L = c.length_m, W = c.width_m, B = c.border_strip_m;

    this._el('rect', {
      x: this._tx(-L/2-B), y: this._ty(W/2+B),
      width: this._ts(L+2*B), height: this._ts(W+2*B), class: 'field-bg',
    });

    const line = (x1,y1,x2,y2) => this._el('line',
      {x1:this._tx(x1),y1:this._ty(y1),x2:this._tx(x2),y2:this._ty(y2),class:'field-line'});
    const rect = (x,y,w,h,cls='field-line') => this._el('rect',
      {x:this._tx(x),y:this._ty(y+h),width:this._ts(w),height:this._ts(h),class:cls});

    rect(-L/2,-W/2,L,W);
    line(0,-W/2,0,W/2);
    this._el('circle',{cx:this._tx(0),cy:this._ty(0),r:this._ts(c.center_circle_r_m),class:'field-line'});
    this._el('circle',{cx:this._tx(0),cy:this._ty(0),r:this._ts(0.05),fill:'white'});

    const pa=c.penalty_area, ga=c.goal_area;
    rect(-L/2,-pa.width_m/2,pa.depth_m,pa.width_m);
    rect(L/2-pa.depth_m,-pa.width_m/2,pa.depth_m,pa.width_m);
    rect(-L/2,-ga.width_m/2,ga.depth_m,ga.width_m);
    rect(L/2-ga.depth_m,-ga.width_m/2,ga.depth_m,ga.width_m);

    const pm=c.penalty_mark_distance_m;
    [[-L/2+pm,0],[L/2-pm,0]].forEach(([px,py])=>
      this._el('circle',{cx:this._tx(px),cy:this._ty(py),r:this._ts(0.06),fill:'white'}));

    const gd=c.goal.depth_m, gw=c.goal.inner_width_m;
    rect(-L/2-gd,-gw/2,gd,gw,'goal');
    rect(L/2,-gw/2,gd,gw,'goal');


    ['g-voronoi','g-heatmap','g-heatmap2','g-trail','g-per-perception','g-udp','g-enemies','g-ball','g-dests','g-robots','g-formation'].forEach(id=>
      this._el('g',{id}));
  }

  // ── Dynamic ──────────────────────────────────────────────────────────
  _render() {
    if (!this._cfg) return;
    this._renderVoronoi();
    this._renderHeatmap();
    this._renderTrail();
    this._renderPerception();
    this._renderUdp();
    this._renderFrame();
  }

  _renderVoronoi() {
    const g = this._svg.getElementById('g-voronoi');
    if (!g) return;
    g.innerHTML = '';

    if (!this._showVoronoi || !this._frame) return;

    const analysis = this.analyzeSpaceControl(this._frame, { respectFilters: true });
    if (!analysis || analysis.sites.length < 2) return;

    for (const site of analysis.sites) {
      const fillColor = this._voronoiFillColor(site);
      const strokeColor = this._voronoiStrokeColor(site);
      this._el('polygon', {
        points: site.cell.map(p => `${this._tx(p.x)},${this._ty(p.y)}`).join(' '),
        fill: fillColor,
        'fill-opacity': site.fillOpacity,
        stroke: strokeColor,
        'stroke-width': '1',
        'stroke-opacity': site.strokeOpacity,
      }, g);
    }
  }

  _renderHeatmap() {
    const g = this._svg.getElementById('g-heatmap');
    if (!g) return;
    g.innerHTML = '';
    const d = this._heatmapData;
    if (!d || !d.max_count) return;
    const L=this._cfg.length_m, W=this._cfg.width_m;
    const cw=this._ts(L/d.bins_x), ch=this._ts(W/d.bins_y);
    for (let row=0;row<d.bins_y;row++) {
      for (let col=0;col<d.bins_x;col++) {
        const v=d.grid[row][col];
        if (!v) continue;
        const alpha=Math.min(1,v/d.max_count);
        const xm=-L/2+col/d.bins_x*L, ym=W/2-row/d.bins_y*W;
        this._el('rect',{
          x:this._tx(xm),y:this._ty(ym),width:cw+0.5,height:ch+0.5,
          fill:`rgba(250,204,21,${alpha})`,class:'heatmap-cell',
        },g);
      }
    }
  }

  _renderTrail() {
    const g=this._svg.getElementById('g-trail');
    if (!g) return;
    g.innerHTML='';
    if (!this._showTrail) return;
    for (const [rid,pts] of Object.entries(this._trailData)) {
      if (!pts.length) continue;
      const color=this.robotColor(parseInt(rid));
      let d='';
      for (const p of pts) {
        const x=this._tx(p.x),y=this._ty(p.y);
        d+=d?`L${x},${y}`:`M${x},${y}`;
      }
      this._el('path',{d,stroke:color,class:'trail-line'},g);
    }
  }

  // ── Main frame ───────────────────────────────────────────────────────
  _renderFrame() {
    const f=this._frame;
    const ge=this._svg.getElementById('g-enemies');
    const gb=this._svg.getElementById('g-ball');
    const gd=this._svg.getElementById('g-dests');
    const gr=this._svg.getElementById('g-robots');
    if (!ge||!gb||!gd||!gr) return;
    ge.innerHTML=''; gb.innerHTML=''; gd.innerHTML=''; gr.innerHTML='';
    if (!f) return;

    const RR = this._ts(0.25);
    const EH = this._ts(0.22);

    // ── Enemies ──────────────────────────────────────────────────────
    if (this._showEnemies) (f.enemies||[]).forEach((e,i)=>{
      const cx=this._tx(e.x), cy=this._ty(e.y);
      const h=EH;
      this._el('polygon',{
        points:`${cx},${cy-h} ${cx+h},${cy} ${cx},${cy+h} ${cx-h},${cy}`,
        fill:'#b91c1c', stroke:'#fca5a5', 'stroke-width':'1.5',
      },ge);
      this._el('text',{
        x:cx, y:cy,
        'font-size':'9', 'font-weight':'700',
        fill:'white', 'text-anchor':'middle', 'dominant-baseline':'central',
      },ge).textContent=`${i+1}`;
    });

    // ── Ball ─────────────────────────────────────────────────────────
    if (this._showBall && f.ball) {
      this._drawBall(gb, this._tx(f.ball.x), this._ty(f.ball.y));
    }

    // ── Our robots ───────────────────────────────────────────────────
    (f.robots||[]).forEach(r=>{
      const inFilter = !this._visibleRobots.size || this._visibleRobots.has(r.id);
      if (!inFilter || !this._visibleBasic.has(r.id)) return;
      const color=this.robotColor(r.id);
      const cx=this._tx(r.x), cy=this._ty(r.y);
      const btLabel = this._formatBtOverlayLabel(r.bt_node);

      if (this._showDest && r.dest) {
        this._el('line',{
          x1:cx,y1:cy,x2:this._tx(r.dest.x),y2:this._ty(r.dest.y),
          stroke:color,'stroke-width':'1','stroke-dasharray':'5 3',opacity:'0.55',
        },gd);
        this._el('circle',{
          cx:this._tx(r.dest.x),cy:this._ty(r.dest.y),r:this._ts(0.09),
          fill:'none',stroke:color,'stroke-width':'1.5','stroke-dasharray':'3 2',
        },gd);
      }

      const fill  = r.lifted ? '#7f1d1d' : color;
      const stroke= r.lifted ? '#fca5a5' : 'rgba(255,255,255,0.9)';
      this._el('circle',{cx,cy,r:RR,fill,stroke,'stroke-width':'2'},gr);

      const cos=Math.cos(r.theta), sin=Math.sin(r.theta);
      this._el('line',{
        x1:cx+cos*RR*0.1, y1:cy-sin*RR*0.1,
        x2:cx+cos*RR*1.35, y2:cy-sin*RR*1.35,
        stroke:'white','stroke-width':'2.5','stroke-linecap':'round',
      },gr);

      if (r.vel_cmd) {
        const {vx, vy} = r.vel_cmd;
        const spd = Math.sqrt(vx*vx + vy*vy);
        if (spd > 0.05) {
          const wdx = (vx*cos - vy*sin) * this._scale;
          const wdy = -(vx*sin + vy*cos) * this._scale;
          const len = spd * this._scale;
          const nx = wdx / (spd * this._scale);
          const ny = wdy / (spd * this._scale);
          const tx = cx + nx*len, ty = cy + ny*len;
          const AH = this._ts(0.13);
          const ang = Math.atan2(ny, nx);
          this._el('line',{x1:cx,y1:cy,x2:tx,y2:ty,
            stroke:'#ef4444','stroke-width':'2','stroke-linecap':'round'},gr);
          this._el('line',{x1:tx,y1:ty,
            x2:tx+Math.cos(ang+2.53)*AH, y2:ty+Math.sin(ang+2.53)*AH,
            stroke:'#ef4444','stroke-width':'2','stroke-linecap':'round'},gr);
          this._el('line',{x1:tx,y1:ty,
            x2:tx+Math.cos(ang-2.53)*AH, y2:ty+Math.sin(ang-2.53)*AH,
            stroke:'#ef4444','stroke-width':'2','stroke-linecap':'round'},gr);
          const s = v => (v >= 0 ? '+' : '') + v.toFixed(2);
          this._el('text',{
            x:cx, y:cy-RR-18,
            'font-size':'8','font-weight':'700',
            fill:'#ef4444',
            stroke:'rgba(5,10,20,0.85)','stroke-width':'2.2','paint-order':'stroke',
            'text-anchor':'middle','dominant-baseline':'auto',
          },gr).textContent = `${s(vx)} ${s(vy)}`;
        }
      }

      const nr=this._ts(0.13);
      this._el('circle',{cx,cy,r:nr,fill:'rgba(0,0,0,0.45)'},gr);
      this._el('text',{
        x:cx, y:cy,
        'font-size':'12','font-weight':'900',
        fill:'white','text-anchor':'middle','dominant-baseline':'central',
      },gr).textContent=String(r.id);

      if (btLabel) {
        this._el('text',{
          x:cx, y:cy-RR-7,
          'font-size':'9','font-weight':'700',
          fill:color,
          stroke:'rgba(5,10,20,0.82)','stroke-width':'2.4','paint-order':'stroke',
          'text-anchor':'middle',
        },gr).textContent = btLabel;
      }

      if (r.lifted) {
        this._el('text',{
          x:cx, y:cy-RR-(btLabel ? 18 : 5),
          'font-size':'9',fill:'#fca5a5','text-anchor':'middle',
        },gr).textContent = '↓Fallen';
      }
    });
  }

  _collectVoronoiSites(frame, options = {}) {
    const { respectFilters = true } = options;
    if (!frame) return [];

    const sites = [];
    for (const r of (frame.robots || [])) {
      const inFilter = !respectFilters
        || ((!this._visibleRobots.size || this._visibleRobots.has(r.id))
            && this._visibleBasic.has(r.id));
      if (!inFilter) continue;
      sites.push({
        key: `robot-${r.id}`,
        team: 'our',
        label: `R${r.id}`,
        x: r.x,
        y: r.y,
        color: this.robotColor(r.id),
        fillOpacity: '0.16',
        strokeOpacity: '0.38',
      });
    }

    if (!respectFilters || this._showEnemies) {
      (frame.enemies || []).forEach((enemy, idx) => {
        sites.push({
          key: `enemy-${idx}`,
          team: 'enemy',
          label: `E${idx + 1}`,
          x: enemy.x,
          y: enemy.y,
          color: this.enemyColor(idx),
          fillOpacity: '0.18',
          strokeOpacity: '0.42',
        });
      });
    }

    return sites;
  }

  _buildVoronoiCell(site, sites) {
    let poly = this._fieldPolygon();
    for (const other of sites) {
      if (other.key === site.key) continue;
      const dx = other.x - site.x;
      const dy = other.y - site.y;
      if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) continue;
      const offset = (other.x * other.x + other.y * other.y - site.x * site.x - site.y * site.y) / 2;
      poly = this._clipPolygonWithHalfPlane(poly, {x: dx, y: dy}, offset);
      if (!poly.length) break;
    }
    return this._dedupePolygon(poly);
  }

  _fieldPolygon() {
    const L = this._cfg.length_m;
    const W = this._cfg.width_m;
    return [
      {x: -L / 2, y: -W / 2},
      {x:  L / 2, y: -W / 2},
      {x:  L / 2, y:  W / 2},
      {x: -L / 2, y:  W / 2},
    ];
  }

  _fieldArea() {
    return this._cfg.length_m * this._cfg.width_m;
  }

  _formatBtOverlayLabel(btNode) {
    if (!btNode) return '';
    const pretty = btNode
      .split('/')
      .pop()
      .replace(/_/g, ' ')
      .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
      .trim();
    return pretty.length > 18 ? `${pretty.slice(0, 17)}…` : pretty;
  }

  _voronoiFillColor(site) {
    if (this._voronoiColorMode === 'team') {
      return site.team === 'our' ? '#3b82f6' : '#dc2626';
    }
    return site.color;
  }

  _voronoiStrokeColor(site) {
    if (this._voronoiColorMode === 'team') {
      return site.team === 'our' ? '#60a5fa' : '#f87171';
    }
    return site.color;
  }

  // Intersect the field polygon with the half-plane that stays closer to `site`.
  _clipPolygonWithHalfPlane(poly, normal, offset) {
    if (!poly.length) return [];
    const EPS = 1e-9;
    const out = [];
    const value = (p) => normal.x * p.x + normal.y * p.y - offset;
    const inside = (p) => value(p) <= EPS;

    for (let i = 0; i < poly.length; i++) {
      const a = poly[i];
      const b = poly[(i + 1) % poly.length];
      const av = value(a);
      const bv = value(b);
      const aIn = av <= EPS;
      const bIn = bv <= EPS;

      if (aIn && bIn) {
        out.push({...b});
        continue;
      }

      if (aIn !== bIn) {
        const t = av / (av - bv);
        out.push({
          x: a.x + (b.x - a.x) * t,
          y: a.y + (b.y - a.y) * t,
        });
      }

      if (!aIn && bIn) out.push({...b});
    }

    return out.filter(inside);
  }

  _dedupePolygon(poly) {
    if (poly.length < 2) return poly;
    const EPS = 1e-6;
    const out = [];
    for (const point of poly) {
      const prev = out[out.length - 1];
      if (!prev || Math.hypot(point.x - prev.x, point.y - prev.y) > EPS) {
        out.push(point);
      }
    }
    if (out.length > 2) {
      const first = out[0];
      const last = out[out.length - 1];
      if (Math.hypot(first.x - last.x, first.y - last.y) <= EPS) out.pop();
    }
    return out;
  }

  _polygonArea(poly) {
    if (poly.length < 3) return 0;
    let area = 0;
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i];
      const b = poly[(i + 1) % poly.length];
      area += a.x * b.y - b.x * a.y;
    }
    return Math.abs(area) * 0.5;
  }

  // ── Per-robot perception ─────────────────────────────────────────────
  // Shape/fill by object type (same visual language as main field):
  //   ball    → small black circle
  //   ally    → circle in robot's own color
  //   enemy   → red diamond
  // Border: thick stroke in the *detecting* robot's color (= "who saw this")
  _renderPerception() {
    const g = this._svg.getElementById('g-per-perception');
    if (!g) return;
    g.innerHTML = '';

    const f = this._frame;
    if (!f || !f.per_perception || !this._visiblePerception.size) return;

    const BR = this._ts(0.10);   // ball radius        (< robot 0.25)
    const AR = this._ts(0.18);   // ally circle radius
    const DH = this._ts(0.18);   // enemy diamond half-size
    const SW = 2.5;              // border stroke-width (= detecting robot's color)

    for (const [ridStr, perc] of Object.entries(f.per_perception)) {
      const rid = parseInt(ridStr);
      if (!this._visiblePerception.has(rid)) continue;
      if (this._visibleRobots.size && !this._visibleRobots.has(rid)) continue;

      const borderColor = this.robotColor(rid);  // thick border = who detected this

      // ── Detected ball: small black circle ─────────────────────────
      if (perc.ball) {
        const cx = this._tx(perc.ball.x);
        const cy = this._ty(perc.ball.y);
        this._el('circle', {
          cx, cy, r: BR,
          fill: '#111111',
          stroke: borderColor,
          'stroke-width': SW,
        }, g);
      }

      // ── Detected robots ────────────────────────────────────────────
      // name='ally' → ally (circle, colored by detected robot's own ID)
      // name='robot' → enemy (red diamond)
      for (const obj of (perc.objects || [])) {
        const cx = this._tx(obj.x);
        const cy = this._ty(obj.y);

        if (obj.name === 'ally') {
          // Ally robot: circle (generic blue, no ID distinction)
          this._el('circle', {
            cx, cy, r: AR,
            fill: '#60a5fa',
            stroke: borderColor,
            'stroke-width': SW,
            opacity: '0.8',
          }, g);
        } else if (obj.name === 'robot') {
          // Enemy robot: red diamond
          const h = DH;
          this._el('polygon', {
            points: `${cx},${cy-h} ${cx+h},${cy} ${cx},${cy+h} ${cx-h},${cy}`,
            fill: '#b91c1c',
            stroke: borderColor,
            'stroke-width': SW,
          }, g);
        }
      }
    }
  }

  // ── UDP team positions ───────────────────────────────────────────────
  // Each entry: team member's circle in their own color + ID, bordered by receiver's color
  _renderUdp() {
    const g = this._svg.getElementById('g-udp');
    if (!g) return;
    g.innerHTML = '';

    const f = this._frame;
    if (!f || !f.udp_perception || !this._visibleUdp.size) return;

    const RU = this._ts(0.22);   // UDP robot radius (slightly smaller than basic)
    const SW = 3.0;              // border stroke-width

    for (const [ridStr, entries] of Object.entries(f.udp_perception)) {
      const receiverId = parseInt(ridStr);
      if (!this._visibleUdp.has(receiverId)) continue;
      if (this._visibleRobots.size && !this._visibleRobots.has(receiverId)) continue;

      const borderColor = this.robotColor(receiverId);

      for (const e of entries) {
        const cx = this._tx(e.x);
        const cy = this._ty(e.y);
        const fillColor = this.robotColor(e.id);

        // Circle in sender's color with receiver's color border
        this._el('circle', {
          cx, cy, r: RU,
          fill: fillColor,
          stroke: borderColor,
          'stroke-width': SW,
          opacity: '0.75',
        }, g);

        // Sender's robot number
        this._el('text', {
          x: cx, y: cy,
          'font-size': '11', 'font-weight': '900',
          fill: 'white', 'text-anchor': 'middle', 'dominant-baseline': 'central',
        }, g).textContent = String(e.id);
      }
    }
  }

  // ── Formation overlay ────────────────────────────────────────────────
  clearFormationOverlay() {
    const g = this._svg.getElementById('g-formation');
    if (g) g.innerHTML = '';
  }

  drawFormationOverlay(robots) {
    const g = this._svg.getElementById('g-formation');
    if (!g) return;
    g.innerHTML = '';
    const pts = (robots || []).filter(r => r.x != null && r.y != null);
    const n = pts.length;
    if (n < 1) return;

    const xs = pts.map(r => r.x), ys = pts.map(r => r.y);
    const cx = xs.reduce((s, x) => s + x, 0) / n;
    const cy = ys.reduce((s, y) => s + y, 0) / n;

    if (n >= 2) {
      const pad = 0.18;
      const minX = Math.min(...xs), maxX = Math.max(...xs);
      const minY = Math.min(...ys), maxY = Math.max(...ys);
      this._el('rect', {
        x: this._tx(minX - pad), y: this._ty(maxY + pad),
        width: this._ts(maxX - minX + 2 * pad),
        height: this._ts(maxY - minY + 2 * pad),
        fill: 'none',
        stroke: 'rgba(96,165,250,0.38)',
        'stroke-width': '1.2',
        'stroke-dasharray': '5 3',
      }, g);
    }

    // centroid dot
    this._el('circle', {
      cx: this._tx(cx), cy: this._ty(cy),
      r: this._ts(0.15),
      fill: 'rgba(96,165,250,0.50)',
      stroke: '#93c5fd',
      'stroke-width': '1.5',
    }, g);
    // crosshair
    const arm = this._ts(0.28);
    const scx = this._tx(cx), scy = this._ty(cy);
    this._el('line', {x1: scx - arm, y1: scy, x2: scx + arm, y2: scy,
      stroke: 'rgba(147,197,253,0.55)', 'stroke-width': '1'}, g);
    this._el('line', {x1: scx, y1: scy - arm, x2: scx, y2: scy + arm,
      stroke: 'rgba(147,197,253,0.55)', 'stroke-width': '1'}, g);
  }

  // ── Ball ─────────────────────────────────────────────────────────────
  _drawBall(g, cx, cy) {
    const R = this._ts(0.14);
    const t = this._el('text', {
      x: cx, y: cy,
      'font-size': R * 2,
      'text-anchor': 'middle',
      'dominant-baseline': 'central',
    }, g);
    t.textContent = '⚽';
  }
}
