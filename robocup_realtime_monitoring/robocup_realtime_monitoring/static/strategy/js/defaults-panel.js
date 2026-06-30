export class DefaultsPanel {
  constructor(opts) {
    this.form = opts.form;            // #defaults-form
    this.tabs = opts.tabs;            // .defaults-tab[]
    this.toggleBtn = opts.toggleBtn;  // #defaults-toggle
    this.card = opts.card;            // #defaults-card
    this.store = opts.store;          // {defaults, onMutate}
    this.currentSpace = "global";

    // Tab click handling
    for (const t of this.tabs) {
      t.addEventListener("click", () => this._switchSpace(t.dataset.space));
    }

    // Apply
    this.form.querySelector("#btn-defaults-apply")
      .addEventListener("click", () => this.apply());

    // Card collapse/expand toggle
    this.toggleBtn.addEventListener("click", () => {
      this.card.classList.toggle("collapsed");
      this.toggleBtn.textContent = this.card.classList.contains("collapsed") ? "▸" : "▾";
    });
  }

  /** Refill the form when store.defaults changes. */
  render() {
    this._loadIntoForm(this.currentSpace);
  }

  _switchSpace(space) {
    if (!space) return;
    // Apply first so unsaved input in the current tab is not lost.
    this.apply({ silent: true });
    this.currentSpace = space;
    for (const t of this.tabs) {
      t.classList.toggle("active", t.dataset.space === space);
    }
    this._loadIntoForm(space);
  }

  _loadIntoForm(space) {
    const ap = (this.store.defaults && this.store.defaults[space]) || {};
    const f = this.form;
    f.action.value = ap.action || "none";
    f.target.value = ap.target || "";
    f.xy.value = ap.xy || "";
    f.note.value = ap.note || "";
  }

  apply(opts = {}) {
    const f = this.form;
    if (!this.store.defaults) this.store.defaults = {};
    const ap = { action: f.action.value };
    if (f.target.value) ap.target = f.target.value;
    if (f.xy.value) ap.xy = f.xy.value;
    if (f.note.value) ap.note = f.note.value;
    this.store.defaults[this.currentSpace] = ap;
    if (!opts.silent && this.store.onMutate) {
      this.store.onMutate({ kind: "defaults", space: this.currentSpace });
    }
  }
}
