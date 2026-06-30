// i18n.js — bilingual UI support (Korean / English)
const LANG_KEY = "strategy_gui_lang";

const STRINGS = {
  ko: {
    "yaml-path-title": "저장 경로",
    "toggle-all-layers-title": "모든 레이어 표시/숨김",
    "hide-all": "전체 숨김",
    "show-all": "전체 표시",
    "robot-status-title": "로봇 상태",
    "robot-status-empty": "실시간 데이터 없음 (UDP 팀통신 대기 중)",
    "layer-hint": "위쪽일수록 코트에서 앞(위)에 그려집니다. ●/◌ 토글로 개별 표시/숨김.",
    "mouse-coord-label": "마우스 좌표:",
    "selected-label": "선택:",
    "selected-none": "(없음)",
    "alt-click-hint": "Alt+클릭: 겹친 zone cycle",
    "live-control-title": "로봇/공 실시간 위치 표시",
    "live-toggle-label": "실시간 위치",
    "live-status-init": "실시간: —",
    "live-status-off": "실시간 OFF",
    "live-status-disconnected": "실시간: 연결 끊김",
    "live-status-no-data": "실시간: 데이터 없음",
    "live-status-active": "실시간: 로봇 {0} · 공 {1}",
    "ball-o": "O",
    "ball-x": "X",
    "toggle-left-collapse": "좌측 패널 접기",
    "toggle-left-expand": "좌측 패널 펼치기",
    "toggle-right-collapse": "우측 패널 접기",
    "toggle-right-expand": "우측 패널 펼치기",
    "zone-card-title": "Zone 속성",
    "zone-form-empty": "왼쪽 코트 또는 Layers 에서 zone 을 선택하세요.",
    "zone-name-label": "이름",
    "zone-xy-ph1": '예: "1;0"',
    "zone-xy-ph2": '예: "7.6;0"',
    "zone-hint-save": "Apply 후 상단 <strong>Save</strong> 로 YAML 에 기록.",
    "z-front-title": "맨 앞으로",
    "z-forward-title": "앞으로",
    "z-backward-title": "뒤로",
    "z-back-title": "맨 뒤로",
    "defaults-toggle-title": "펼치기/접기",
    "vis-toggle-title": "표시/숨김",
    "save-dirty": "● 미저장 변경 있음",
    "save-loaded": "로드 완료",
    "save-saved": "✓ 저장됨 ({0} zones)",
    "save-init-failed": "초기화 실패: {0}",
    "new-zone-name": "새 zone {0}",
    "confirm-reload": "미저장 변경이 있습니다. 무시하고 다시 로드할까요?",
    "confirm-leave": "미저장 변경이 있습니다. 무시하고 나갈까요?",
    "alert-id-required": "id 는 필수입니다",
    "alert-id-exists": "id '{0}' 가 이미 존재합니다",
    "confirm-delete-zone": "zone '{0}' 를 삭제하시겠습니까?",
    "act-move_to": "이동 (move_to)",
    "act-turn_to": "조준 (turn_to)",
    "act-kick": "킥! (kick)",
    "act-pass": "패스 (pass)",
    "act-dribble": "드리블 (dribble)",
    "act-stop_move": "정지 (stop_move)",
    "act-spin_search": "공 탐색 (spin_search)",
    "act-recheck_wait": "재확인 대기 (recheck_wait)",
    "act-save_ball_to_destination": "공 위치 저장 (save_ball_to_destination)",
    "act-mark_buildup_passed": "빌드업 패스 (mark_buildup_passed)",
    "act-reset_buildup_pass": "빌드업 리셋 (reset_buildup_pass)",
    "conn-title": "마지막 수신 경과",
    "pen-title": "penalty 상태",
    "comm-label": "팀 통신",
    "row-action": "동작",
    "row-pose": "pose",
    "row-conf": "위치 신뢰도",
    "row-ball": "공",
    "row-ballpos": "공 위치",
    "tgl-own-ball": "본인 공",
    "tgl-fused-ball": "융합 공",
    "tgl-fused-enemy": "융합 적",
    "comm-ok-title": "communication_check = true (동료 로봇 패킷 수신 중)",
    "comm-bad-title": "communication_check = false (동료 로봇 패킷 미수신)",
    "act-val-title": "move_to: 공 추격(초록 화살표) · turn_to: 골대 조준 · kick: 조준 중 공 이동",
    "ball-detecting": "감지 중",
    "ball-not-detecting": "미감지",
    "overlay-on-fmt": "{0} 오버레이 켜짐 (클릭해 토글)",
    "overlay-off-fmt": "{0} 오버레이 꺼짐 (클릭해 토글)",
    "field-coord-label": "필드 좌표",
    "lbl-opponent": "상대",
    "lbl-ball": "공",
    "lbl-fused-ball": "융합공",
    "lbl-fused-enemy": "융합적",
    "lang-btn": "EN",
  },
  en: {
    "yaml-path-title": "Save path",
    "toggle-all-layers-title": "Show/Hide all layers",
    "hide-all": "Hide All",
    "show-all": "Show All",
    "robot-status-title": "Robot Status",
    "robot-status-empty": "No live data (waiting for UDP team comm)",
    "layer-hint": "Higher items are drawn in front. ●/◌ toggles individual visibility.",
    "mouse-coord-label": "Cursor:",
    "selected-label": "Selected:",
    "selected-none": "(none)",
    "alt-click-hint": "Alt+click: cycle overlapping zones",
    "live-control-title": "Show live robot/ball position",
    "live-toggle-label": "Live",
    "live-status-init": "Live: —",
    "live-status-off": "Live: OFF",
    "live-status-disconnected": "Live: disconnected",
    "live-status-no-data": "Live: no data",
    "live-status-active": "Live: {0} robots · ball {1}",
    "ball-o": "O",
    "ball-x": "X",
    "toggle-left-collapse": "Collapse left panel",
    "toggle-left-expand": "Expand left panel",
    "toggle-right-collapse": "Collapse right panel",
    "toggle-right-expand": "Expand right panel",
    "zone-card-title": "Zone Properties",
    "zone-form-empty": "Select a zone from the court or Layers.",
    "zone-name-label": "Name",
    "zone-xy-ph1": 'e.g. "1;0"',
    "zone-xy-ph2": 'e.g. "7.6;0"',
    "zone-hint-save": "Click Apply then <strong>Save</strong> at top to write to YAML.",
    "z-front-title": "To front",
    "z-forward-title": "Forward",
    "z-backward-title": "Backward",
    "z-back-title": "To back",
    "defaults-toggle-title": "Expand/Collapse",
    "vis-toggle-title": "Show/Hide",
    "save-dirty": "● Unsaved changes",
    "save-loaded": "Loaded",
    "save-saved": "✓ Saved ({0} zones)",
    "save-init-failed": "Init failed: {0}",
    "new-zone-name": "new zone {0}",
    "confirm-reload": "You have unsaved changes. Reload anyway?",
    "confirm-leave": "You have unsaved changes. Leave anyway?",
    "alert-id-required": "ID is required",
    "alert-id-exists": "ID '{0}' already exists",
    "confirm-delete-zone": "Delete zone '{0}'?",
    "act-move_to": "Move (move_to)",
    "act-turn_to": "Aim (turn_to)",
    "act-kick": "Kick! (kick)",
    "act-pass": "Pass (pass)",
    "act-dribble": "Dribble (dribble)",
    "act-stop_move": "Stop (stop_move)",
    "act-spin_search": "Ball search (spin_search)",
    "act-recheck_wait": "Recheck wait (recheck_wait)",
    "act-save_ball_to_destination": "Save ball pos. (save_ball_to_destination)",
    "act-mark_buildup_passed": "Buildup pass (mark_buildup_passed)",
    "act-reset_buildup_pass": "Buildup reset (reset_buildup_pass)",
    "conn-title": "Time since last packet",
    "pen-title": "penalty status",
    "comm-label": "Team comm",
    "row-action": "Action",
    "row-pose": "pose",
    "row-conf": "Pos. confidence",
    "row-ball": "Ball",
    "row-ballpos": "Ball pos.",
    "tgl-own-ball": "Own ball",
    "tgl-fused-ball": "Fused ball",
    "tgl-fused-enemy": "Fused enemy",
    "comm-ok-title": "communication_check = true (receiving teammate packets)",
    "comm-bad-title": "communication_check = false (not receiving teammate packets)",
    "act-val-title": "move_to: chasing ball (green arrow) · turn_to: aiming at goal · kick: ball moving while aiming",
    "ball-detecting": "detected",
    "ball-not-detecting": "not detected",
    "overlay-on-fmt": "{0} overlay on (click to toggle)",
    "overlay-off-fmt": "{0} overlay off (click to toggle)",
    "field-coord-label": "field coords",
    "lbl-opponent": "opp",
    "lbl-ball": "ball",
    "lbl-fused-ball": "fused-ball",
    "lbl-fused-enemy": "fused-enemy",
    "lang-btn": "KO",
  },
};

let _lang = localStorage.getItem(LANG_KEY) || "en";
const _listeners = [];

export function getLang() { return _lang; }

export function setLang(lang) {
  if (!STRINGS[lang]) return;
  _lang = lang;
  localStorage.setItem(LANG_KEY, lang);
  document.documentElement.lang = lang;
  applyToDOM();
  _listeners.forEach((fn) => fn(lang));
}

export function t(key, ...args) {
  let s = (STRINGS[_lang] || STRINGS.ko)[key];
  if (s == null) s = STRINGS.ko[key] ?? key;
  if (args.length) args.forEach((v, i) => { s = s.replace(`{${i}}`, String(v)); });
  return s;
}

export function onLangChange(fn) { _listeners.push(fn); }

export function applyToDOM() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => {
    el.innerHTML = t(el.dataset.i18nHtml);
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.title = t(el.dataset.i18nTitle);
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPh);
  });
}

export function initLang() {
  document.documentElement.lang = _lang;
  applyToDOM();
}
