import { t } from "./i18n.js";

export class ActionPanel {
  constructor(formEl, emptyEl, store) {
    this.form = formEl;
    this.empty = emptyEl;
    this.store = store;
    this.currentId = null;

    this.form.querySelector("select[name=type]").addEventListener("change", () => {
      this._toggleGeomFields();
    });

    this.form.querySelector("#btn-apply").addEventListener("click", () => this.apply());
    this.form.querySelector("#btn-delete").addEventListener("click", () => this.delete());
  }

  show(zone) {
    if (!zone) {
      this.currentId = null;
      this.form.classList.add("hidden");
      this.empty.classList.remove("hidden");
      return;
    }
    this.currentId = zone.id;
    this.form.classList.remove("hidden");
    this.empty.classList.add("hidden");

    const f = this.form;
    f.id.value = zone.id;
    f.name.value = zone.name || "";
    f.type.value = zone.type;
    f.space.value = zone.space || "global";
    f.bt_ref.value = zone.bt_ref || "";
    f.color.value = zone.color || "#3498db";

    if (zone.type === "rect") {
      f.x1.value = zone.geometry.x1 ?? 0;
      f.y1.value = zone.geometry.y1 ?? 0;
      f.x2.value = zone.geometry.x2 ?? 0;
      f.y2.value = zone.geometry.y2 ?? 0;
    } else if (zone.type === "circle") {
      f.cx.value = zone.geometry.cx ?? 0;
      f.cy.value = zone.geometry.cy ?? 0;
      f.r.value = zone.geometry.r ?? 1;
    }

    const ap = zone.action_policy || {};
    f.action.value = ap.action || "none";
    f.target.value = ap.target || "";
    f.xy.value = ap.xy || "";
    f.note.value = ap.note || "";

    this._toggleGeomFields();
  }

  _toggleGeomFields() {
    const t = this.form.type.value;
    this.form.querySelector("#geom-rect").classList.toggle("hidden", t !== "rect");
    this.form.querySelector("#geom-circle").classList.toggle("hidden", t !== "circle");
  }

  /** Apply form values back into the matching zone in store.zones. */
  apply() {
    if (!this.currentId) return;
    const zone = this.store.zones.find((z) => z.id === this.currentId);
    if (!zone) return;

    const f = this.form;
    const newId = String(f.id.value).trim();
    if (!newId) { alert(t("alert-id-required")); return; }
    if (newId !== zone.id) {
      if (this.store.zones.some((z) => z.id === newId)) {
        alert(t("alert-id-exists", newId));
        return;
      }
      zone.id = newId;
      this.currentId = newId;
      this.store.selectedId = newId;
    }
    zone.name = f.name.value;
    zone.type = f.type.value;
    zone.space = f.space.value;
    zone.bt_ref = f.bt_ref.value;
    zone.color = f.color.value;

    if (zone.type === "rect") {
      zone.geometry = {
        x1: parseFloat(f.x1.value),
        y1: parseFloat(f.y1.value),
        x2: parseFloat(f.x2.value),
        y2: parseFloat(f.y2.value),
      };
    } else {
      zone.geometry = {
        cx: parseFloat(f.cx.value),
        cy: parseFloat(f.cy.value),
        r: parseFloat(f.r.value),
      };
    }

    const ap = { action: f.action.value };
    if (f.target.value) ap.target = f.target.value;
    if (f.xy.value) ap.xy = f.xy.value;
    if (f.note.value) ap.note = f.note.value;
    zone.action_policy = ap;

    if (this.store.onMutate) this.store.onMutate(zone);
  }

  delete() {
    if (!this.currentId) return;
    if (!confirm(t("confirm-delete-zone", this.currentId))) return;
    const idx = this.store.zones.findIndex((z) => z.id === this.currentId);
    if (idx >= 0) this.store.zones.splice(idx, 1);
    this.currentId = null;
    this.store.selectedId = null;
    this.show(null);
    if (this.store.onMutate) this.store.onMutate(null);
  }
}
