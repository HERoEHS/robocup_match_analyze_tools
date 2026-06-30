import { t } from "./i18n.js";

export class LayerPanel {
  constructor(listEl, countEl, store) {
    this.list = listEl;
    this.countEl = countEl;
    this.store = store;
  }

  render() {
    this.list.innerHTML = "";
    const zones = this.store.zones;
    this.countEl.textContent = `(${zones.length})`;

    // Put items rendered on top (later in YAML) at the top of the list.
    const ordered = zones.slice().reverse();
    for (const z of ordered) {
      this.list.appendChild(this._renderItem(z));
    }
  }

  _renderItem(z) {
    const li = document.createElement("li");
    li.className = "layer-item";
    if (z.id === this.store.selectedId) li.classList.add("selected");
    if (this.store.isHidden(z.id)) li.classList.add("hidden-zone");

    // Visibility toggle
    const vis = document.createElement("button");
    vis.className = "vis";
    vis.type = "button";
    vis.title = t("vis-toggle-title");
    vis.textContent = this.store.isHidden(z.id) ? "◌" : "●";
    vis.addEventListener("click", (e) => {
      e.stopPropagation();
      this.store.toggleHidden(z.id);
    });
    li.appendChild(vis);

    // Color chip
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.style.background = z.color || "#999";
    li.appendChild(chip);

    // Name + type
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = z.name || z.id;
    name.title = `${z.id}\ntype=${z.type}, space=${z.space}`;
    li.appendChild(name);

    // Space badge
    const badge = document.createElement("span");
    badge.className = "badge " + (z.space || "global");
    badge.textContent = (z.type || "") + " / " + (z.space || "");
    li.appendChild(badge);

    li.addEventListener("click", () => {
      this.store.selectZone(z.id);
    });
    return li;
  }
}
