import { CourtRenderer } from './court.js';
import { HeatmapLayer } from './heatmap-layer.js';

const _fetchWithTimeout = (input, init, timeoutMs = 60000) => {
  const ctrl = new AbortController();
  const tid = setTimeout(() => ctrl.abort(), timeoutMs);
  return fetch(input, { ...init, signal: ctrl.signal }).finally(() => clearTimeout(tid));
};
const api  = (path) => _fetchWithTimeout(path, {}).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); });
const post = (path, body) => _fetchWithTimeout(path, {
  method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body),
}).then(r => { if(!r.ok) return r.json().then(e=>{throw new Error(e.detail||r.statusText);}); return r.json(); });

// ── i18n ──────────────────────────────────────────────────────────────────────
const I18N = {
  ko: {
    sessionPlaceholder: '(세션 선택)',
    btnLoad:       '불러오기',
    btnDownload:   '병합 다운로드',
    btnSavePng:    'PNG 저장',
    btnRefresh:    '목록 새로고침',
    btnPathApply:  '적용',
    labelTime:     '시간',
    labelHeatmap:  '히트맵',
    labelTrail:    '이동경로',
    labelDest:     '목적지',
    labelVoronoi:  '보로노이',
    labelFormation: '형태',
    labelSeekStep: '이동',
    formationTitle:      '팀 형태',
    formationChartLabel: '무게중심 추이',
    formationCentroid:   '무게중심',
    formationWidth:      '폭',
    formationDepth:      '깊이',
    formationAvgDist:    '밀집도',
    formationFwd:        '공격 진영',
    formationAttack:     '공격 진영',
    formationDefend:     '수비 진영',
    formationTipCentroid:'팀 로봇 위치 평균 (x>0 = 공격 진영)',
    formationTipWidth:   '로봇들의 공격↔수비 방향 분산 폭',
    formationTipDepth:   '로봇들의 좌↔우 방향 분산 폭',
    formationTipAvgDist: '로봇 간 평균 거리 — 낮을수록 밀집',
    formationTipFwd:     '공격 진영(x>0)에 위치한 로봇 수',
    eventBookmarks:'이벤트',
    eventBookmarksNone: '북마크 가능한 이벤트가 없습니다.',
    eventBookmarksFilteredEmpty: '선택한 마커 종류에 해당하는 이벤트가 없습니다.',
    eventFilterTitle: '마커',
    eventTypeState: '경기 상태',
    eventTypeSetplay: '세트플레이',
    eventTypeGoal:  '득점',
    eventTypeFall:  '넘어짐',
    eventTypeKick:  '킥 이벤트',
    eventTypeBt:    'BT 전환',
    eventTypeStateShort: '상태',
    eventTypeSetplayShort: '세트',
    eventTypeGoalShort:  '득점',
    eventTypeFallShort:  '넘어짐',
    eventTypeKickShort:  '킥',
    eventTypeBtShort:    'BT',
    eventSetplayOff: '세트플레이 종료',
    eventStateFmt:  (state) => `${state} 전환`,
    eventSetplayFmt:(name) => name ? `${name} 시작` : '세트플레이 종료',
    eventGoalOurFmt:(score) => `우리팀 득점 · ${score}점`,
    eventGoalOppFmt:(team, score) => `상대팀(${team}) 득점 · ${score}점`,
    eventGoalTeamFmt:(team, score) => `Team ${team} 득점 · ${score}점`,
    eventGoalShortOur: '우리팀 득점',
    eventGoalShortOpp: '상대팀 득점',
    eventFallFmt:   (rid) => `넘어짐 R${rid}`,
    eventKickFmt:   (rid) => `킥 R${rid}`,
    eventBtFmt:     (rid, node) => `BT R${rid} ${node}`,
    voronoiModeIndividual: '로봇별',
    voronoiModeTeam:       '팀 2색',
    spaceControlTitle:      '공간 점유율',
    spaceControlScope:      '전체 팀 기준',
    spaceControlCurrent:    '현재',
    spaceControlAverage:    '현재까지 평균',
    spaceControlTimeline:   '점유율 추이',
    spaceControlBreakdown:  '현재 로봇별 점유율',
    spaceControlNoData:     '상대 위치 데이터가 있으면 공간 점유율 분석을 표시합니다.',
    spaceControlUnavailable:'데이터 부족',
    spaceControlCurrentFmt: (our, enemy) => `우리 ${our.toFixed(1)}% · 상대 ${enemy.toFixed(1)}%`,
    spaceControlAverageFmt: (our, enemy) => `우리 ${our.toFixed(1)}% · 상대 ${enemy.toFixed(1)}%`,
    allRobots:     '전체',
    opponent:      '상대팀',
    ourTeam:       '우리팀',
    ball:          '공',
    ourRobots:     '우리팀 로봇',
    enemyRobots:   '상대팀 로봇',
    pos:           '위치',
    angle:         'θ',
    btNode:        'BT',
    fallen:        '↓ 넘어짐',
    noEnemies:     '감지된 상대 없음',
    labelBall:     '공',
    labelEnemies:  '상대 로봇',
    basicLabel:    '기본 표시',
    visionLabel:   '비전',
    visionBall:    '공 인식',
    visionObj:     '물체 인식',
    udpLabel:      'UDP 수신',
    udpLegend:     'UDP 위치',
    firstHalf:     '전반',
    secondHalf:    '후반',
    loading:       '로딩 중…',
    parsing:       'MCAP 파싱 중…',
    noSessions:    (dir)     => `세션 없음 — ${dir}`,
    sessionCount:  (n, dir)  => `${n}개 세션 — ${dir}`,
    loadDone:      (s, ids)  => `로드 완료 — ${s}s, 로봇 ${ids}`,
    loadErr:       (msg)     => `오류: ${msg}`,
    downloadPreparing: '병합 파일 생성 중…',
    downloadDone:  (name)    => `다운로드 완료 — ${name}`,
    downloadErr:   (msg)     => `다운로드 오류: ${msg}`,
    pathErr:       (msg)     => `경로 오류: ${msg}`,
    fileBrowserEmpty:     '경로를 설정하면 파일 목록이 표시됩니다.',
    fileBrowserSelectAll: '전체 선택',
    fileBrowserNoneSelected: '파일을 1개 이상 선택하세요.',
    fileBrowserInfo: (n, g) => `${n}개 파일 / ${g}개 폴더`,
    robotSelectLabel: '로봇 선택',
    robotLabel:    (id)      => `Robot ${id}`,
    filterLabel:   (id)      => `R${id}`,
    robotOption:   (id)      => `Robot ${id}`,
    langBtn:       'EN',
    poseSourceLoc:    'Loc',
    poseSourceUdp:    'UDP',
    srcOurRobots:     'localization / udp',
    srcBall:          'detected_objects · 합산',
    srcEnemies:       'cooperative_perception',
    enemySource:      '협력인식',
    ballNoData:       '공 데이터 없음',
    ballAge:          (s) => `${s.toFixed(1)}s 전`,
    toggleBrowserLabel: '파일 선택',
    hmModeRobot:    '로봇 활동',
    hmModeBall:     '공 이동',
    hmModeKick:     '킥 위치',
    hmTimeProgressive: '현재까지 (누적)',
    hmTimeAll:      '전체 경기',
    hmTimeFirst:    '전반',
    hmTimeSecond:   '후반',
    hmTimeSegment:  '선택 구간',
    segmentBar:     '사용자 구간 만들기',
    segmentTitle:   '선택 구간',
    segmentEmpty:   '세그먼트를 선택하거나 Start/End로 사용자 구간을 만들어 주세요.',
    segmentSetA:    '시작점 = 현재',
    segmentSetB:    '끝점 = 현재',
    segmentAdd:     '구간 추가',
    segmentClear:   '선택 해제',
    segmentLoop:    '반복',
    segmentFilterTitle: '종류',
    segmentListEmpty: '사용 가능한 세그먼트가 없습니다.',
    segmentFilteredEmpty: '선택한 세그먼트 종류에 해당하는 구간이 없습니다.',
    segmentTypeStateSpan: '경기 상태 구간',
    segmentTypeSetplaySpan: '세트플레이 구간',
    segmentTypeGoalWindow: '득점 전후 구간',
    segmentTypeFallWindow: '넘어짐 전후 구간',
    segmentTypeCustom: '사용자 구간',
    segmentTypeStateSpanShort: '상태',
    segmentTypeSetplaySpanShort: '세트',
    segmentTypeGoalWindowShort: '득점',
    segmentTypeFallWindowShort: '넘어짐',
    segmentTypeCustomShort: '사용자',
    segmentStateSpanFmt: (state) => `${state} 구간`,
    segmentSetplaySpanFmt: (name) => name ? `${name} 구간` : '세트플레이 구간',
    segmentGoalWindowFmt: (label) => `${label} 득점 전후`,
    segmentFallWindowFmt: (rid) => `넘어짐 전후 R${rid}`,
    segmentCustomFmt: (name) => name || '사용자 구간',
    segmentDraftFmt:  (t0, t1) => `Start ${t0.toFixed(1)}s → End ${t1.toFixed(1)}s`,
    segmentSavedFmt:  (n) => `사용자 구간 ${n}`,
    segmentDurationFmt: (s) => `${s.toFixed(1)}s`,
    segmentRange:     '구간',
    segmentDuration:  '길이',
    segmentStatsRobots: '활성 로봇',
    segmentStatsDistance: '총 이동거리 (전 로봇 합산)',
    segmentStatsKicks: '킥',
    segmentStatsFalls: '넘어짐',
    segmentStatsMaxSpeed: '최대 속도',
    segmentStatsSpaceAvg: '평균 공간 점유',
    segmentStatsSpacingCentroid: '평균 무게중심',
    segmentStatsSpacingWidth:    '평균 폭 / 깊이',
    segmentStatsSpacingDist:     '평균 밀집도',
    segmentStatsSpacingFwd:      '공격 진영 평균',
    segmentStatsUnavailable: '선택 구간 통계가 없습니다.',
    segmentStatsLoading: '구간 통계 계산 중…',
    segmentRobotBreakdown: '로봇별 요약',
    segmentSpaceAvgFmt: (our, enemy) => `우리 ${our.toFixed(1)}% · 상대 ${enemy.toFixed(1)}%`,
    summaryTitle:         '경기 요약',
    summaryFull:          '전체',
    summaryFirst:         '전반',
    summarySecond:        '후반',
    summaryDuration:      '경기 시간',
    summaryActiveRobots:  '활성 로봇',
    summaryTotalDist:     '총 이동거리',
    summaryTotalKicks:    '킥 횟수',
    summaryTotalFalls:    '넘어짐',
    summaryMaxSpeed:      '최고 속도',
    summaryRobotBreakdown:'로봇별',
    summaryDistFmt:       (m) => `${m.toFixed(1)} m`,
    summarySpeedFmt:      (v) => `${v.toFixed(2)} m/s`,
    possessionTitle:         '볼 소유권',
    possessionOur:           '우리',
    possessionEnemy:         '상대',
    possessionLoose:         'loose',
    possessionTurnoverLost:  '잃음',
    possessionTurnoverGained:'탈취',
    possessionNoEnemy:       '상대 위치 데이터 없음',
    possessionBallZone:      '공 구역 분포',
    possessionZoneLeft:      '왼쪽 (x < -1.5m)',
    possessionZoneMid:       '중앙 (-1.5 ~ 1.5m)',
    possessionZoneRight:     '오른쪽 (x > 1.5m)',
    possessionTipOur:        '공에서 점유 판정 거리 이내의 가장 가까운 로봇이 우리팀인 구간 비율 (loose 제외)',
    possessionTipEnemy:      '공에서 점유 판정 거리 이내의 가장 가까운 로봇이 상대팀인 구간 비율 (loose 제외)',
    possessionTipLoose:      '어느 팀도 점유 판정 거리 이내에 없는 구간 비율',
    possessionTipLost:       '우리팀 → 상대팀으로 소유권이 넘어간 횟수 (최소 점유 지속 시간 이상 유지된 전환만 카운트)',
    possessionTipGained:     '상대팀 → 우리팀으로 소유권을 탈취한 횟수 (최소 점유 지속 시간 이상 유지된 전환만 카운트)',
    possessionTipZone:       '공이 머문 필드 구역 분포. 좌표계 방향은 경기마다 다를 수 있음',
    possessionLiveOur:       '우리팀 점유 중',
    possessionLiveEnemy:     '상대팀 점유 중',
    possessionLiveLoose:     '공 경합 중',
    possessionLiveStuck:     '공 끼임 (양팀 접촉)',
    possessionStuck:         '끼임',
    possessionTipStuck:      '양팀 로봇이 동시에 공 임계거리 이내 — 어느 팀도 단독 점유 불가',
    possTimelineTitle:       '점유 추이',
    possZoneFlowLabel:       '공 이동 흐름',
    possZoneFlowLM:          '좌↔중',
    possZoneFlowMR:          '중↔우',
    possZoneFlowLR:          '좌↔우',
    possZoneFlowTip:         '공이 구역 간 이동한 횟수 (0.5초 이상 체류한 전환만 카운트)',
    setplayPostPoss:         '세트플레이 후 점유 (5초)',
    setplayPostPossOur:      '우리팀 점유',
    setplayPostPossEnemy:    '상대팀 점유',
    setplayPostPossLoose:    '경합',
    settingsTitle:           '⚙ 설정',
    settingsPossessionDist:  '점유 판정 거리',
    settingsPossessionDistHint: '공에서 이 거리 이내의 로봇이 공을 점유 중으로 판정',
    settingsPossessionHold:  '최소 점유 지속 시간',
    settingsPossessionHoldHint: '이 시간 이상 유지된 전환만 턴오버로 카운트',
    settingsApply:           '적용',
    teamPickerLabel:         '우리팀',
    teamPickerPlaceholder:   '팀 선택',
    teamPickerOptionFmt:     (n) => `Team ${n}`,
  },
  en: {
    sessionPlaceholder: '(Select session)',
    btnLoad:       'Load',
    btnDownload:   'Download merged',
    btnSavePng:    'Save PNG',
    btnRefresh:    'Refresh',
    btnPathApply:  'Apply',
    labelTime:     'Time',
    labelHeatmap:  'Heatmap',
    labelTrail:    'Trail',
    labelDest:     'Destination',
    labelVoronoi:  'Voronoi',
    labelFormation: 'Formation',
    labelSeekStep: 'Seek',
    formationTitle:      'Team Formation',
    formationChartLabel: 'Centroid trend',
    formationCentroid:   'Centroid',
    formationWidth:      'Width',
    formationDepth:      'Depth',
    formationAvgDist:    'Compactness',
    formationFwd:        'Fwd robots',
    formationAttack:     'Attack half',
    formationDefend:     'Defend half',
    formationTipCentroid:'Average robot position (x>0 = attack half)',
    formationTipWidth:   'Robot spread along attack↔defense axis',
    formationTipDepth:   'Robot spread along left↔right axis',
    formationTipAvgDist: 'Mean inter-robot distance — lower = more compact',
    formationTipFwd:     'Robots in attack half (x>0)',
    eventBookmarks:'Events',
    eventBookmarksNone: 'No bookmarkable events.',
    eventBookmarksFilteredEmpty: 'No events match the current marker filters.',
    eventFilterTitle: 'Markers',
    eventTypeState: 'Match state',
    eventTypeSetplay: 'Setplay',
    eventTypeGoal:  'Goal',
    eventTypeFall:  'Fall',
    eventTypeKick:  'Kick event',
    eventTypeBt:    'BT transition',
    eventTypeStateShort: 'State',
    eventTypeSetplayShort: 'Setplay',
    eventTypeGoalShort:  'Goal',
    eventTypeFallShort:  'Fall',
    eventTypeKickShort:  'Kick',
    eventTypeBtShort:    'BT',
    eventSetplayOff: 'Setplay cleared',
    eventStateFmt:  (state) => `Changed to ${state}`,
    eventSetplayFmt:(name) => name ? `${name} started` : 'Setplay cleared',
    eventGoalOurFmt:(score) => `Our goal · ${score}`,
    eventGoalOppFmt:(team, score) => `Opponent (${team}) goal · ${score}`,
    eventGoalTeamFmt:(team, score) => `Team ${team} goal · ${score}`,
    eventGoalShortOur: 'Our goal',
    eventGoalShortOpp: 'Opp goal',
    eventFallFmt:   (rid) => `Fall R${rid}`,
    eventKickFmt:   (rid) => `Kick R${rid}`,
    eventBtFmt:     (rid, node) => `BT R${rid} ${node}`,
    voronoiModeIndividual: 'Per robot',
    voronoiModeTeam:       'Two-team',
    spaceControlTitle:      'Space Control',
    spaceControlScope:      'Whole team basis',
    spaceControlCurrent:    'Current',
    spaceControlAverage:    'Avg so far',
    spaceControlTimeline:   'Control trend',
    spaceControlBreakdown:  'Current per-robot share',
    spaceControlNoData:     'Space control analysis appears when opponent positions are available.',
    spaceControlUnavailable:'Insufficient data',
    spaceControlCurrentFmt: (our, enemy) => `Our ${our.toFixed(1)}% · Opp ${enemy.toFixed(1)}%`,
    spaceControlAverageFmt: (our, enemy) => `Our ${our.toFixed(1)}% · Opp ${enemy.toFixed(1)}%`,
    allRobots:     'All',
    opponent:      'Opponent',
    ourTeam:       'Our Team',
    ball:          'Ball',
    ourRobots:     'Our Robots',
    enemyRobots:   'Enemy Robots',
    pos:           'Pos',
    angle:         'Angle',
    btNode:        'BT',
    fallen:        '↓ Fallen',
    noEnemies:     'No enemies detected',
    labelBall:     'Ball',
    labelEnemies:  'Enemies',
    basicLabel:    'Basic',
    visionLabel:   'Vision',
    visionBall:    'Ball detect',
    visionObj:     'Obj detect',
    udpLabel:      'UDP recv',
    udpLegend:     'UDP pos',
    firstHalf:     '1st Half',
    secondHalf:    '2nd Half',
    loading:       'Loading…',
    parsing:       'Parsing MCAP…',
    noSessions:    (dir)     => `No sessions — ${dir}`,
    sessionCount:  (n, dir)  => `${n} sessions — ${dir}`,
    loadDone:      (s, ids)  => `Loaded — ${s}s, robots ${ids}`,
    loadErr:       (msg)     => `Error: ${msg}`,
    downloadPreparing: 'Preparing merged download…',
    downloadDone:  (name)    => `Downloaded — ${name}`,
    downloadErr:   (msg)     => `Download error: ${msg}`,
    pathErr:       (msg)     => `Path error: ${msg}`,
    fileBrowserEmpty:     'Set a path to see files.',
    fileBrowserSelectAll: 'Select all',
    fileBrowserNoneSelected: 'Select at least one file.',
    fileBrowserInfo: (n, g) => `${n} files / ${g} folders`,
    robotSelectLabel: 'Select robots',
    robotLabel:    (id)      => `Robot ${id}`,
    filterLabel:   (id)      => `R${id}`,
    robotOption:   (id)      => `Robot ${id}`,
    langBtn:       '한국어',
    poseSourceLoc:    'Loc',
    poseSourceUdp:    'UDP',
    srcOurRobots:     'localization / udp',
    srcBall:          'detected_objects · merged',
    srcEnemies:       'cooperative_perception',
    enemySource:      'coop.perc.',
    ballNoData:       'No ball data',
    ballAge:          (s) => `${s.toFixed(1)}s ago`,
    toggleBrowserLabel: 'Select files',
    hmModeRobot:    'Robot activity',
    hmModeBall:     'Ball movement',
    hmModeKick:     'Kick positions',
    hmTimeProgressive: 'Until now (cumulative)',
    hmTimeAll:      'Full match',
    hmTimeFirst:    '1st Half',
    hmTimeSecond:   '2nd Half',
    hmTimeSegment:  'Selected segment',
    segmentBar:     'Create custom segment',
    segmentTitle:   'Selected Segment',
    segmentEmpty:   'Select a segment or create a custom Start/End segment.',
    segmentSetA:    'Start = Now',
    segmentSetB:    'End = Now',
    segmentAdd:     'Add segment',
    segmentClear:   'Clear selection',
    segmentLoop:    'Loop',
    segmentFilterTitle: 'Kinds',
    segmentListEmpty: 'No segments available.',
    segmentFilteredEmpty: 'No segments match the current filters.',
    segmentTypeStateSpan: 'Match-state span',
    segmentTypeSetplaySpan: 'Setplay span',
    segmentTypeGoalWindow: 'Goal window',
    segmentTypeFallWindow: 'Fall window',
    segmentTypeCustom: 'Custom segment',
    segmentTypeStateSpanShort: 'State',
    segmentTypeSetplaySpanShort: 'Setplay',
    segmentTypeGoalWindowShort: 'Goal',
    segmentTypeFallWindowShort: 'Fall',
    segmentTypeCustomShort: 'Custom',
    segmentStateSpanFmt: (state) => `${state} span`,
    segmentSetplaySpanFmt: (name) => name ? `${name} span` : 'Setplay span',
    segmentGoalWindowFmt: (label) => `Around ${label} goal`,
    segmentFallWindowFmt: (rid) => `Around fall R${rid}`,
    segmentCustomFmt: (name) => name || 'Custom segment',
    segmentDraftFmt:  (t0, t1) => `Start ${t0.toFixed(1)}s → End ${t1.toFixed(1)}s`,
    segmentSavedFmt:  (n) => `Custom ${n}`,
    segmentDurationFmt: (s) => `${s.toFixed(1)}s`,
    segmentRange:     'Range',
    segmentDuration:  'Duration',
    segmentStatsRobots: 'Active robots',
    segmentStatsDistance: 'Distance (all robots)',
    segmentStatsKicks: 'Kicks',
    segmentStatsFalls: 'Falls',
    segmentStatsMaxSpeed: 'Peak speed',
    segmentStatsSpaceAvg: 'Avg space control',
    segmentStatsSpacingCentroid: 'Avg centroid',
    segmentStatsSpacingWidth:    'Avg width / depth',
    segmentStatsSpacingDist:     'Avg compactness',
    segmentStatsSpacingFwd:      'Avg fwd robots',
    segmentStatsUnavailable: 'No stats for the selected segment.',
    segmentStatsLoading: 'Computing segment stats…',
    segmentRobotBreakdown: 'Per-robot summary',
    segmentSpaceAvgFmt: (our, enemy) => `Our ${our.toFixed(1)}% · Opp ${enemy.toFixed(1)}%`,
    summaryTitle:         'Match Summary',
    summaryFull:          'Full',
    summaryFirst:         '1st Half',
    summarySecond:        '2nd Half',
    summaryDuration:      'Duration',
    summaryActiveRobots:  'Active robots',
    summaryTotalDist:     'Total distance',
    summaryTotalKicks:    'Total kicks',
    summaryTotalFalls:    'Total falls',
    summaryMaxSpeed:      'Peak speed',
    summaryRobotBreakdown:'Per robot',
    summaryDistFmt:       (m) => `${m.toFixed(1)} m`,
    summarySpeedFmt:      (v) => `${v.toFixed(2)} m/s`,
    possessionTitle:         'Ball Possession',
    possessionOur:           'Our',
    possessionEnemy:         'Opp',
    possessionLoose:         'loose',
    possessionTurnoverLost:  'lost',
    possessionTurnoverGained:'gained',
    possessionNoEnemy:       'No enemy position data',
    possessionBallZone:      'Ball zone',
    possessionZoneLeft:      'Left (x < -1.5m)',
    possessionZoneMid:       'Center (-1.5 ~ 1.5m)',
    possessionZoneRight:     'Right (x > 1.5m)',
    possessionTipOur:        'Share of time the nearest robot within the possession distance was ours (loose excluded)',
    possessionTipEnemy:      'Share of time the nearest robot within the possession distance was the opponent (loose excluded)',
    possessionTipLoose:      'Share of samples where no robot was within the possession distance of the ball',
    possessionTipLost:       'Times possession switched our→opponent (only transitions sustained ≥ min hold time)',
    possessionTipGained:     'Times possession switched opponent→our (only transitions sustained ≥ min hold time)',
    possessionTipZone:       'Distribution of ball position across field thirds. Field orientation may vary per game.',
    possessionLiveOur:       'Our team has the ball',
    possessionLiveEnemy:     'Opponent has the ball',
    possessionLiveLoose:     'Ball is loose',
    possessionLiveStuck:     'Ball stuck (both teams)',
    possessionStuck:         'stuck',
    possessionTipStuck:      'Both teams have a robot within the threshold distance — neither has sole possession',
    possTimelineTitle:       'Possession trend',
    possZoneFlowLabel:       'Ball movement',
    possZoneFlowLM:          'L↔C',
    possZoneFlowMR:          'C↔R',
    possZoneFlowLR:          'L↔R',
    possZoneFlowTip:         'Number of ball zone transitions (only transitions with ≥0.5s dwell counted)',
    setplayPostPoss:         'Post-setplay possession (5s)',
    setplayPostPossOur:      'Our possession',
    setplayPostPossEnemy:    'Opp possession',
    setplayPostPossLoose:    'Contested',
    settingsTitle:           '⚙ Settings',
    settingsPossessionDist:  'Possession distance',
    settingsPossessionDistHint: 'Robot is considered in possession when within this distance of the ball',
    settingsPossessionHold:  'Min. possession hold time',
    settingsPossessionHoldHint: 'Only transitions held this long are counted as turnovers',
    settingsApply:           'Apply',
    teamPickerLabel:         'Our Team',
    teamPickerPlaceholder:   'Select team',
    teamPickerOptionFmt:     (n) => `Team ${n}`,
  },
};

let lang = localStorage.getItem('lang') || 'en';
const t = (key, ...args) => {
  const v = I18N[lang][key];
  return typeof v === 'function' ? v(...args) : v;
};

function renderTeamPicker() {
  const wrap = document.getElementById('team-picker-wrap');
  const sel  = document.getElementById('team-picker-select');
  if (!wrap || !sel) return;

  document.getElementById('team-picker-label').textContent = t('teamPickerLabel') + ':';

  if (_sessionTeamNumbers.length <= 1) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  sel.innerHTML = `<option value="0">${t('teamPickerPlaceholder')}</option>`;
  for (const n of _sessionTeamNumbers) {
    const opt = document.createElement('option');
    opt.value = n;
    opt.textContent = t('teamPickerOptionFmt', n);
    if (n === _ourTeamNumber) opt.selected = true;
    sel.appendChild(opt);
  }
}

function applyLang() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const val = I18N[lang][key];
    if (val && typeof val === 'string') el.textContent = val;
  });
  document.querySelectorAll('[data-robot-label]').forEach(el => {
    const rid = parseInt(el.getAttribute('data-robot-label'));
    el.textContent = t('robotLabel', rid);
  });
  $('btn-lang').textContent = t('langBtn');
  document.documentElement.lang = lang;
  court.setLang(lang);
  renderSegments();
  renderGameSummary();
  _updateToggleBtn();
  updateSegmentSummary();
  renderTeamPicker();
  if (!sessionKey) updateBallCard(null);
}

// ── Constants ─────────────────────────────────────────────────────────────────
const STATE_NAMES = {
  ko: {0:'INITIAL',1:'READY',2:'SET',3:'PLAYING',4:'FINISHED'},
  en: {0:'INITIAL',1:'READY',2:'SET',3:'PLAYING',4:'FINISHED'},
};
const SETPLAY_NAMES = {
  ko: {0:'',1:'직접 FK',2:'간접 FK',3:'페널티 킥',4:'스로인',5:'골킥',6:'코너킥'},
  en: {0:'',1:'DIRECT FK',2:'INDIRECT FK',3:'PENALTY KICK',4:'THROW IN',5:'GOAL KICK',6:'CORNER KICK'},
};
const EVENT_KINDS = ['state', 'setplay', 'goal', 'fall', 'kick', 'bt'];
const visibleEventKinds = new Set(EVENT_KINDS);
const SEGMENT_KINDS = ['state_span', 'setplay_span', 'goal_window', 'fall_window', 'custom'];
const SEGMENT_KIND_ROW = { state_span: 0, setplay_span: 1, goal_window: 2, fall_window: 3, custom: 4 };
const SEGMENT_ROW_STRIDE = 7;

const stateName  = (s) => STATE_NAMES[lang][s]   ?? String(s);
const setplayName= (s) => SETPLAY_NAMES[lang][s] ?? '';

// ── State ─────────────────────────────────────────────────────────────────────
let sessionKey = null, duration = 0, robotIds = [];
let _ourTeamNumber = 0;
let _sessionTeamNumbers = [];
let currentT = 0, playing = false, playRaf = null, lastWall = null, speed = 1;
let seekStepSec = 1.0;
let eventBookmarks = [];
let robotGaps = {};
let loopSelectedSegment = false;
let segmentDraftA = null, segmentDraftB = null;
let gameSummary = null;
let summaryHalf = 'full';
let possessionDistM = parseFloat(localStorage.getItem('possession_dist_m') ?? '0.5');
let possessionHoldS = parseFloat(localStorage.getItem('possession_hold_s') ?? '0.1');
function possessionParams() {
  return `possession_dist_m=${possessionDistM.toFixed(2)}&possession_hold_s=${possessionHoldS.toFixed(2)}`;
}
const _selectedFiles = new Set();  // File paths selected via checkboxes
let heatmapEnabled = false, trailEnabled = false;
let hmLayer = null, hmPreload = null;
let scSamplesPreload = null, scTimeline = [];
let possPreload = null;
let spacingTimeline = null;
let segmentPresets = [];
let customSegments = [];
let selectedSegmentId = null;
let selectedSegmentStats = null;
let segmentStatsPending = false;
let segmentStatsSeq = 0;
let customSegmentCounter = 0;
let downloadBusy = false;
const visibleRobots     = new Set();
const visiblePerception = new Set();
const visibleBasic      = new Set();
const visibleUdp        = new Set();
const visibleSegmentKinds = new Set(SEGMENT_KINDS);
const collapsedSegmentGroups = new Set(SEGMENT_KINDS);

// ── DOM refs ──────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const elLoad            = $('btn-load');
const elRefresh         = $('btn-refresh');
const elDownload        = $('btn-download');
const elSavePng         = $('btn-save-png');
const elInfo            = $('session-info');
const elFileBrowser     = $('file-browser');
const elToggleBrowser   = $('btn-toggle-browser');
const elPathInput = $('path-input');
const elPathApply = $('btn-path-apply');
const elTime    = $('time-display');
const elTl           = $('timeline');
const elPlay         = $('btn-play');
const elTlSegments   = $('timeline-segments');
const elTlSegmentPoints = $('timeline-segment-points');
const elTlMarkers    = $('timeline-markers');
const elTlGaps       = $('timeline-gaps');
const elTimelineStack= $('timeline-stack');
const elTlTooltip    = $('timeline-tooltip');
const elSeekStep     = $('seek-step-select');
const elSpeed        = $('speed-select');
const elBookmarkList = $('bookmark-list');
const elBookmarkFilter = $('bookmark-filter');
const elSegmentSetA  = $('btn-segment-set-a');
const elSegmentSetB  = $('btn-segment-set-b');
const elSegmentLoop  = $('segment-loop-toggle');
const elLoadProgressWrap  = $('load-progress-wrap');
const elLoadSpinner       = $('load-spinner');
const elLoadProgressLabel = $('load-progress-label');
const elSegmentList = $('segment-list');
const elSegmentFilter = $('segment-filter');
const elSegmentEmpty = $('segment-empty');
const elSegmentContent = $('segment-content');
const elSegmentName = $('segment-name');
const elSegmentRange = $('segment-range');
const elSegmentBadges = $('segment-badges');
const elSegmentOverview = $('segment-overview');
const elSegmentRobotBreakdown = $('segment-robot-breakdown');
const elSegmentAdd = $('btn-segment-add');
const elSegmentClear = $('btn-segment-clear');
const elHm      = $('heatmap-toggle');
const elHmMode  = $('heatmap-mode-select');
const elHmRobot = $('heatmap-robot-select');
const elHmTime  = $('heatmap-time-select');
const elTrail   = $('trail-toggle');
const elDest    = $('dest-toggle');
const elBall    = $('ball-toggle');
const elEnemies = $('enemy-toggle');
const elVoronoi = $('voronoi-toggle');
const elVoronoiColorMode = $('voronoi-color-mode-select');
const elFormationToggle = $('formation-toggle');
const elFormationSection = $('formation-section');
const elFormationRealtime = $('formation-realtime');
const elFormationChartBlock = $('formation-chart-block');
const elFormationChart = $('formation-chart');
const elFilter  = $('robot-filter');
const elCards   = $('robot-cards');
const elEnemy   = $('enemy-cards');
const elBallCard = $('ball-card');
const elBtnLang = $('btn-lang');
const elScEmpty         = $('space-control-empty');
const elScContent       = $('space-control-content');
const elScCurrentText   = $('space-current-text');
const elScAverageText   = $('space-average-text');
const elScCurrentOur    = $('space-current-our');
const elScCurrentEnemy  = $('space-current-enemy');
const elScAverageOur    = $('space-average-our');
const elScAverageEnemy  = $('space-average-enemy');
const elScChart         = $('space-control-chart');
const elScBreakdown     = $('space-breakdown-list');

// ── Tooltip ────────────────────────────────────────────────────────────────────
const elTip = $('ui-tooltip');
let _tipShowing = false;

function _showTip(el, mx, my) {
  if (!elTip) return;
  const text = lang === 'en'
    ? (el.dataset.tipEn || el.dataset.tipKo)
    : (el.dataset.tipKo || el.dataset.tipEn);
  if (!text) return;
  elTip.textContent = text;
  _tipShowing = true;
  elTip.classList.add('tip-show');
  _moveTip(mx, my);
}
function _hideTip() {
  if (!elTip) return;
  _tipShowing = false;
  elTip.classList.remove('tip-show');
}
function _moveTip(mx, my) {
  if (!elTip || !_tipShowing) return;
  const tw = elTip.offsetWidth, th = elTip.offsetHeight;
  const left = (mx + 14 + tw > window.innerWidth)  ? mx - tw - 8 : mx + 14;
  const top  = (my + 18 + th > window.innerHeight) ? my - th - 8 : my + 18;
  elTip.style.left = left + 'px';
  elTip.style.top  = top  + 'px';
}
document.addEventListener('mouseover', e => {
  const el = e.target.closest('[data-tip-ko],[data-tip-en]');
  if (el) _showTip(el, e.clientX, e.clientY);
  else _hideTip();
});
document.addEventListener('mousemove', e => _moveTip(e.clientX, e.clientY));

// ── Chart popup ────────────────────────────────────────────────────────────────
const elChartPopup      = $('chart-popup');
const elChartPopupTitle = $('chart-popup-title');
const elChartPopupBody  = $('chart-popup-body');

let _popupSvgEl = null, _popupOrigParent = null, _popupOrigNextSib = null, _popupOrigStyle = '', _popupOrigPar = null;
let _dragState  = null;

function openChartPopup(svgEl, title) {
  if (!elChartPopup || !svgEl) return;
  closeChartPopup();
  _popupSvgEl       = svgEl;
  _popupOrigParent  = svgEl.parentNode;
  _popupOrigNextSib = svgEl.nextSibling;
  _popupOrigStyle   = svgEl.getAttribute('style') || '';
  _popupOrigPar     = svgEl.getAttribute('preserveAspectRatio');
  elChartPopupTitle.textContent = title;
  svgEl.style.cssText = 'width:100%;height:100%;display:block;';
  svgEl.setAttribute('preserveAspectRatio', 'none');
  elChartPopupBody.appendChild(svgEl);
  elChartPopup.hidden = false;
}

function closeChartPopup() {
  if (!elChartPopup || elChartPopup.hidden) return;
  if (_popupSvgEl && _popupOrigParent) {
    if (_popupOrigStyle) _popupSvgEl.setAttribute('style', _popupOrigStyle);
    else _popupSvgEl.removeAttribute('style');
    if (_popupOrigPar !== null) _popupSvgEl.setAttribute('preserveAspectRatio', _popupOrigPar);
    else _popupSvgEl.removeAttribute('preserveAspectRatio');
    _popupOrigParent.insertBefore(_popupSvgEl, _popupOrigNextSib || null);
  }
  elChartPopup.hidden = true;
  _popupSvgEl = null; _popupOrigParent = null; _popupOrigNextSib = null; _popupOrigPar = null;
}

$('chart-popup-header')?.addEventListener('mousedown', e => {
  if (e.button !== 0) return;
  const r = elChartPopup.getBoundingClientRect();
  const savedL = r.left, savedT = r.top;
  elChartPopup.style.transform = 'none';
  elChartPopup.style.left = savedL + 'px';
  elChartPopup.style.top  = savedT + 'px';
  _dragState = { sx: e.clientX, sy: e.clientY, pl: savedL, pt: savedT };
  e.preventDefault();
});
document.addEventListener('mousemove', e => {
  if (!_dragState) return;
  elChartPopup.style.left = (_dragState.pl + e.clientX - _dragState.sx) + 'px';
  elChartPopup.style.top  = (_dragState.pt + e.clientY - _dragState.sy) + 'px';
});
document.addEventListener('mouseup', () => { _dragState = null; });
$('chart-popup-close')?.addEventListener('click', closeChartPopup);

const elGoScore      = $('go-score');
const elGoState      = $('go-state');
const elGoSetplay    = $('go-setplay');
const elGoTime       = $('go-time');
const elGoPossession = $('go-possession');
const elGoTeamA      = $('go-team-a');
const elGoTeamB      = $('go-team-b');

const court = new CourtRenderer($('court'));

elScChart?.addEventListener('click', () => openChartPopup(elScChart, t('spaceControlTimeline')));
elFormationChart?.addEventListener('click', () => openChartPopup(elFormationChart, t('formationChartLabel')));
$('summary-team')?.addEventListener('click', e => {
  const svgEl = e.target.closest('.poss-timeline-svg');
  if (svgEl) openChartPopup(svgEl, t('possTimelineTitle'));
});

$('summary-tabs')?.addEventListener('click', (e) => {
  const tab = e.target.closest('.summary-tab');
  if (!tab || tab.hidden) return;
  summaryHalf = tab.dataset.half;
  renderGameSummary();
});

// ── Settings panel ────────────────────────────────────────────────────────────
function initSettingsPanel() {
  const btnToggle  = $('btn-settings-toggle');
  const body       = $('settings-body');
  const inputDist  = $('input-possession-dist');
  const inputHold  = $('input-possession-hold');
  const btnApply   = $('btn-settings-apply');
  if (!btnToggle || !body) return;

  // Populate inputs from current values
  inputDist.value = possessionDistM.toFixed(2);
  inputHold.value = possessionHoldS.toFixed(2);

  btnToggle.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = !body.hidden;
    body.hidden = open;
    btnToggle.setAttribute('aria-expanded', String(!open));
  });

  // Close on outside click
  document.addEventListener('click', (e) => {
    if (!body.hidden && !body.contains(e.target) && e.target !== btnToggle) {
      body.hidden = true;
      btnToggle.setAttribute('aria-expanded', 'false');
    }
  });

  btnApply.addEventListener('click', async () => {
    const d = parseFloat(inputDist.value);
    const h = parseFloat(inputHold.value);
    if (isNaN(d) || isNaN(h) || d <= 0 || h <= 0) return;
    possessionDistM = d;
    possessionHoldS = h;
    localStorage.setItem('possession_dist_m', d.toFixed(2));
    localStorage.setItem('possession_hold_s', h.toFixed(2));

    if (!sessionKey) return;
    btnApply.disabled = true;
    try {
      const [summary, newPossPreload] = await Promise.all([
        api(`/api/game_summary?session_key=${encodeURIComponent(sessionKey)}&${possessionParams()}`),
        api(`/api/possession_preload?session_key=${encodeURIComponent(sessionKey)}&${possessionParams()}`).catch(() => null),
      ]);
      gameSummary = summary;
      possPreload = newPossPreload;
      renderGameSummary();
      await refreshSelectedSegmentStats();
    } catch(e) {
      console.warn('settings apply failed:', e);
    } finally {
      btnApply.disabled = false;
    }
  });
}
initSettingsPanel();

function updateDownloadButton() {
  if (!elDownload) return;
  elDownload.disabled = !sessionKey || downloadBusy || elLoad.disabled;
  if (elSavePng) elSavePng.disabled = !sessionKey || elLoad.disabled;
}

// ── Language toggle ───────────────────────────────────────────────────────────
elBtnLang.addEventListener('click', () => {
  lang = lang === 'ko' ? 'en' : 'ko';
  localStorage.setItem('lang', lang);
  applyLang();
});

// ── File browser ──────────────────────────────────────────────────────────────
function _populateFileBrowser(data) {
  _selectedFiles.clear();
  elFileBrowser.innerHTML = '';
  elPathInput.value = data.data_dir;
  elPathInput.classList.remove('error');

  const groups = data.groups || [];
  if (!groups.length) {
    const empty = document.createElement('div');
    empty.className = 'fb-empty muted';
    empty.setAttribute('data-i18n', 'fileBrowserEmpty');
    empty.textContent = t('fileBrowserEmpty');
    elFileBrowser.appendChild(empty);
    elInfo.textContent = t('noSessions', data.data_dir);
    return;
  }

  let totalFiles = 0;
  for (const group of groups) {
    // Group header
    const hdr = document.createElement('div');
    hdr.className = 'fb-group-hdr';

    const dirLabel = document.createElement('span');
    dirLabel.className = 'fb-dir-name';
    dirLabel.textContent = group.dir + '/';

    const selAll = document.createElement('button');
    selAll.className = 'fb-sel-all';
    selAll.textContent = t('fileBrowserSelectAll');
    selAll.dataset.tipKo = '이 폴더의 파일 모두 선택';
    selAll.dataset.tipEn = 'Select all files in this folder';
    selAll.addEventListener('click', () => {
      const rows = hdr.nextElementSibling?.querySelectorAll('.fb-row');
      rows?.forEach(row => {
        const cb = row.querySelector('input[type=checkbox]');
        if (cb && !cb.checked) cb.click();
      });
    });

    hdr.appendChild(dirLabel);
    hdr.appendChild(selAll);
    elFileBrowser.appendChild(hdr);

    // File rows wrapper
    const rowsWrap = document.createElement('div');
    rowsWrap.className = 'fb-rows';

    for (const file of group.files) {
      const row = document.createElement('label');
      row.className = 'fb-row';
      row.dataset.tipKo = `${file.name}\n크기: ${(file.size_bytes/1024/1024).toFixed(1)}MB`;
      row.dataset.tipEn = `${file.name}\nSize: ${(file.size_bytes/1024/1024).toFixed(1)}MB`;

      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.value = file.path;
      cb.addEventListener('change', () => {
        if (cb.checked) _selectedFiles.add(file.path);
        else _selectedFiles.delete(file.path);
        _updateToggleBtn();
      });

      const rid = document.createElement('span');
      rid.className = 'fb-rid';
      if (file.robot_id !== null) {
        rid.textContent = `R${file.robot_id}`;
        rid.style.color = court.robotColor(file.robot_id);
      } else {
        rid.textContent = '?';
      }

      const name = document.createElement('span');
      name.className = 'fb-name';
      name.textContent = file.name;

      const size = document.createElement('span');
      size.className = 'fb-size muted';
      size.textContent = (file.size_bytes / 1024 / 1024).toFixed(1) + 'MB';

      const dt = new Date(file.mtime * 1000);
      const date = document.createElement('span');
      date.className = 'fb-date muted';
      date.textContent = `${dt.getMonth()+1}/${String(dt.getDate()).padStart(2,'0')} `
        + `${String(dt.getHours()).padStart(2,'0')}:${String(dt.getMinutes()).padStart(2,'0')}`;

      row.appendChild(cb);
      row.appendChild(rid);
      row.appendChild(name);
      row.appendChild(size);
      row.appendChild(date);
      rowsWrap.appendChild(row);
      totalFiles++;
    }
    elFileBrowser.appendChild(rowsWrap);
  }

  elInfo.textContent = t('fileBrowserInfo', totalFiles, groups.length);
}

async function refreshSessions() {
  const data = await api('/api/sessions');
  _populateFileBrowser(data);
}

elRefresh.addEventListener('click', refreshSessions);

// ── File browser toggle ───────────────────────────────────────────────────────
function _updateToggleBtn() {
  const n = _selectedFiles.size;
  const open = elFileBrowser.classList.contains('open');
  const label = t('toggleBrowserLabel');
  elToggleBrowser.textContent = n > 0
    ? `${label} (${n}) ${open ? '▴' : '▾'}`
    : `${label} ${open ? '▴' : '▾'}`;
  elToggleBrowser.classList.toggle('has-selection', n > 0);
}

elToggleBrowser.addEventListener('click', () => {
  elFileBrowser.classList.toggle('open');
  _updateToggleBtn();
});

document.addEventListener('click', e => {
  if (!elFileBrowser.classList.contains('open')) return;
  if (!elFileBrowser.contains(e.target) && e.target !== elToggleBrowser) {
    elFileBrowser.classList.remove('open');
    _updateToggleBtn();
  }
});

// ── Path bar ──────────────────────────────────────────────────────────────────
async function applyPath() {
  const path = elPathInput.value.trim();
  if (!path) return;
  elPathApply.disabled = true;
  try {
    const data = await post('/api/data_dir', { path });
    _populateFileBrowser(data);
    elPathInput.classList.remove('error');
  } catch (e) {
    elPathInput.classList.add('error');
    elInfo.textContent = t('pathErr', e.message);
  }
  elPathApply.disabled = false;
}
elPathApply.addEventListener('click', applyPath);
elPathInput.addEventListener('keydown', e => { if (e.key === 'Enter') applyPath(); });

function isInteractiveElement(el) {
  return !!el && (
    el.isContentEditable ||
    el.closest('input, textarea, select, button, label')
  );
}

function prettifyBtNode(btNode) {
  if (!btNode) return '';
  return btNode
    .replace(/_/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .trim();
}

function formatEventTime(t_) {
  return `${t_.toFixed(1)}s`;
}

function round3(v) {
  return Math.round(v * 1000) / 1000;
}

function clampTime(t_) {
  return Math.max(0, Math.min(Number(t_) || 0, duration));
}

function isOurTeamNumber(teamNumber) {
  if (_ourTeamNumber === 0) return false;
  return Number(teamNumber) === _ourTeamNumber;
}

function formatGoalTeamLabel(teamNumber) {
  const team = Number(teamNumber ?? 0);
  if (isOurTeamNumber(team)) return lang === 'ko' ? '우리팀' : 'Our team';
  if (team > 0) return lang === 'ko' ? `상대팀(${team})` : `Opponent (${team})`;
  return lang === 'ko' ? '득점' : 'Goal';
}

function formatGoalDetail(event, options = {}) {
  const short = !!options.short;
  const teamNumber = Number(event?.team_number ?? 0);
  const score = Number(event?.score ?? 0);
  if (isOurTeamNumber(teamNumber)) {
    return short ? t('eventGoalShortOur') : t('eventGoalOurFmt', score);
  }
  if (teamNumber > 0) {
    return short ? t('eventGoalShortOpp') : t('eventGoalOppFmt', teamNumber, score);
  }
  return short ? 'Goal' : t('eventGoalTeamFmt', '?', score);
}

function eventAccentColor(event) {
  if (!event) return '#f8fafc';
  if (event.kind === 'kick') {
    const rid = Number(event.robot_id ?? 0);
    return rid > 0 ? court.robotColor(rid) : '#f8fafc';
  }
  if (event.kind === 'goal' || event.kind === 'fall') {
    return '#f87171';
  }
  return '#f8fafc';
}

function eventKindAccent(kind) {
  if (kind === 'state') return '#93c5fd';
  if (kind === 'setplay') return '#fbbf24';
  if (kind === 'goal') return '#f87171';
  if (kind === 'fall') return '#f87171';
  if (kind === 'kick') return '#4ade80';
  if (kind === 'bt') return '#c4b5fd';
  return '#f8fafc';
}

function getVisibleEventBookmarks() {
  return eventBookmarks.filter(event => visibleEventKinds.has(event.kind));
}

function normalizeEventBookmarks(events) {
  const order = { state: 0, setplay: 1, goal: 2, fall: 3, kick: 4, bt: 5 };
  return (events || [])
    .filter(event => Number.isFinite(event?.t) && event.t >= 0)
    .sort((a, b) => (
      a.t - b.t ||
      (order[a.kind] ?? 99) - (order[b.kind] ?? 99) ||
      ((a.team_number ?? 0) - (b.team_number ?? 0)) ||
      ((a.robot_id ?? 0) - (b.robot_id ?? 0))
    ))
    .map((event, index) => ({ ...event, _index: index }));
}

function formatEventLabel(event, options = {}) {
  const short = !!options.short;
  if (!event) return '';
  if (event.kind === 'state') return stateName(event.state);
  if (event.kind === 'setplay') {
    const sp = setplayName(event.set_play);
    return sp || t('eventSetplayOff');
  }
  if (event.kind === 'goal') return formatGoalDetail(event, { short });
  if (event.kind === 'fall') return t('eventFallFmt', event.robot_id ?? '?');
  if (event.kind === 'kick') return t('eventKickFmt', event.robot_id ?? '?');
  if (event.kind === 'bt') {
    const node = prettifyBtNode(event.bt_node || '');
    return short ? `R${event.robot_id ?? '?'} ${node}` : t('eventBtFmt', event.robot_id ?? '?', node);
  }
  return short ? 'Event' : 'Event';
}

function formatEventTypeLabel(event, options = {}) {
  const short = !!options.short;
  const kind = typeof event === 'string' ? event : event?.kind;
  if (!kind) return '';
  if (kind === 'state') return short ? t('eventTypeStateShort') : t('eventTypeState');
  if (kind === 'setplay') return short ? t('eventTypeSetplayShort') : t('eventTypeSetplay');
  if (kind === 'goal') return short ? t('eventTypeGoalShort') : t('eventTypeGoal');
  if (kind === 'fall') return short ? t('eventTypeFallShort') : t('eventTypeFall');
  if (kind === 'kick') return short ? t('eventTypeKickShort') : t('eventTypeKick');
  if (kind === 'bt') return short ? t('eventTypeBtShort') : t('eventTypeBt');
  return 'Event';
}

function formatEventDetail(event) {
  if (!event) return '';
  if (event.kind === 'state') {
    return t('eventStateFmt', stateName(event.state));
  }
  if (event.kind === 'setplay') {
    return t('eventSetplayFmt', setplayName(event.set_play));
  }
  if (event.kind === 'goal') {
    return formatGoalDetail(event);
  }
  if (event.kind === 'fall') {
    return t('eventFallFmt', event.robot_id ?? '?');
  }
  if (event.kind === 'kick') {
    return t('eventKickFmt', event.robot_id ?? '?');
  }
  if (event.kind === 'bt') {
    return t('eventBtFmt', event.robot_id ?? '?', prettifyBtNode(event.bt_node || ''));
  }
  return formatEventLabel(event);
}

function eventKindClass(kind) {
  return ['state', 'setplay', 'goal', 'fall', 'kick', 'bt'].includes(kind) ? kind : 'other';
}

function segmentKindClass(kind) {
  return kind ? String(kind).replace(/_/g, '-') : 'other';
}

function normalizeSegments(segments) {
  const order = {
    state_span: 0,
    setplay_span: 1,
    goal_window: 2,
    fall_window: 3,
    custom: 4,
  };
  return (segments || [])
    .filter(seg => Number.isFinite(seg?.t0) && Number.isFinite(seg?.t1) && seg.t1 > seg.t0)
    .sort((a, b) => (
      a.t0 - b.t0 ||
      a.t1 - b.t1 ||
      (order[a.kind] ?? 99) - (order[b.kind] ?? 99) ||
      ((a.robot_id ?? 0) - (b.robot_id ?? 0))
    ))
    .map((seg, index) => ({ ...seg, _index: index }));
}

function getDraftSegment() {
  if (!Number.isFinite(segmentDraftA) || !Number.isFinite(segmentDraftB)) return null;
  const t0 = Math.max(0, Math.min(segmentDraftA, segmentDraftB));
  const t1 = Math.min(duration, Math.max(segmentDraftA, segmentDraftB));
  if (t1 <= t0) return null;
  return {
    id: 'draft',
    kind: 'custom',
    t0, t1,
    duration: t1 - t0,
    draft: true,
    label: t('segmentDraftFmt', t0, t1),
  };
}

function getAllSegments() {
  const segments = [...segmentPresets, ...customSegments];
  const draft = getDraftSegment();
  if (draft) segments.unshift(draft);
  return normalizeSegments(segments);
}

function getSegmentById(id) {
  if (!id) return null;
  return getAllSegments().find(seg => seg.id === id) || null;
}

function getSelectedSegment() {
  return getSegmentById(selectedSegmentId);
}

function getSelectedSegmentRange() {
  const seg = getSelectedSegment();
  return seg ? [seg.t0, seg.t1] : null;
}

function getDraftPointMarkers() {
  const pts = [];
  if (Number.isFinite(segmentDraftA)) {
    pts.push({
      label: t('segmentSetA'),
      t: round3(clampTime(segmentDraftA)),
      role: 'start',
    });
  }
  if (Number.isFinite(segmentDraftB)) {
    pts.push({
      label: t('segmentSetB'),
      t: round3(clampTime(segmentDraftB)),
      role: 'end',
    });
  }
  return pts;
}

function formatSegmentTypeLabel(segment, options = {}) {
  const { short = false } = options;
  const kind = typeof segment === 'string' ? segment : segment?.kind;
  if (kind === 'state_span') return t(short ? 'segmentTypeStateSpanShort' : 'segmentTypeStateSpan');
  if (kind === 'setplay_span') return t(short ? 'segmentTypeSetplaySpanShort' : 'segmentTypeSetplaySpan');
  if (kind === 'goal_window') return t(short ? 'segmentTypeGoalWindowShort' : 'segmentTypeGoalWindow');
  if (kind === 'fall_window') return t(short ? 'segmentTypeFallWindowShort' : 'segmentTypeFallWindow');
  return t(short ? 'segmentTypeCustomShort' : 'segmentTypeCustom');
}

function formatSegmentLabel(segment) {
  if (!segment) return '';
  if (segment.kind === 'state_span') {
    return t('segmentStateSpanFmt', stateName(segment.state));
  }
  if (segment.kind === 'setplay_span') {
    return t('segmentSetplaySpanFmt', setplayName(segment.set_play));
  }
  if (segment.kind === 'goal_window') {
    return t('segmentGoalWindowFmt', formatGoalTeamLabel(segment.team_number));
  }
  if (segment.kind === 'fall_window') {
    return t('segmentFallWindowFmt', segment.robot_id ?? '?');
  }
  if (segment.draft) {
    return t('segmentDraftFmt', segment.t0, segment.t1);
  }
  if (Number.isFinite(segment.custom_index)) {
    return segment.label || t('segmentSavedFmt', segment.custom_index);
  }
  return t('segmentCustomFmt', segment.label || '');
}

function segmentAccentColor(segment) {
  if (!segment) return '#f8fafc';
  if (segment.kind === 'state_span') return '#93c5fd';
  if (segment.kind === 'setplay_span') return '#fbbf24';
  if (segment.kind === 'goal_window') return '#fb923c';
  if (segment.kind === 'fall_window') return '#f87171';
  return '#c4b5fd';
}

function getVisibleSegments() {
  return getAllSegments().filter(segment => visibleSegmentKinds.has(segment.kind));
}


function renderSegmentFilterButtons(segments = getAllSegments()) {
  if (!elSegmentFilter) return;
  const availableKinds = new Set(segments.map(segment => segment.kind));
  elSegmentFilter.innerHTML = '';

  for (const kind of SEGMENT_KINDS) {
    const btn = document.createElement('button');
    const active = visibleSegmentKinds.has(kind);
    const available = availableKinds.has(kind);
    btn.type = 'button';
    btn.className = `marker-filter-btn ${segmentKindClass(kind)}${active ? ' active' : ''}`;
    btn.textContent = formatSegmentTypeLabel(kind, { short: true });
    btn.title = formatSegmentTypeLabel(kind);
    btn.dataset.tipKo = `${formatSegmentTypeLabel(kind)} 구간 표시/숨김`;
    btn.dataset.tipEn = `Toggle ${formatSegmentTypeLabel(kind)} segments`;
    btn.disabled = !available;
    btn.setAttribute('aria-pressed', String(active));
    btn.style.setProperty('--marker-color', segmentAccentColor({ kind }));
    btn.addEventListener('click', () => {
      if (visibleSegmentKinds.has(kind)) visibleSegmentKinds.delete(kind);
      else visibleSegmentKinds.add(kind);
      const selected = getSelectedSegment();
      if (selected && !visibleSegmentKinds.has(selected.kind)) {
        clearSelectedSegment({ rerender: false, refreshHeatmapToo: true });
      }
      renderSegments();
    });
    elSegmentFilter.appendChild(btn);
  }
}

function hideTimelineTooltip() {
  if (!elTlTooltip) return;
  elTlTooltip.hidden = true;
  elTlTooltip.textContent = '';
}

function showTimelineInfoTooltip(anchorEl, kindText, timeText, detailText) {
  if (!anchorEl || !elTlTooltip || !elTimelineStack) {
    hideTimelineTooltip();
    return;
  }

  elTlTooltip.innerHTML = '';
  const kindEl = document.createElement('div');
  kindEl.className = 'timeline-tooltip-kind';
  kindEl.textContent = kindText;
  const timeEl = document.createElement('div');
  timeEl.className = 'timeline-tooltip-time';
  timeEl.textContent = timeText;
  const detailEl = document.createElement('div');
  detailEl.className = 'timeline-tooltip-detail';
  detailEl.textContent = detailText;
  elTlTooltip.appendChild(kindEl);
  elTlTooltip.appendChild(timeEl);
  elTlTooltip.appendChild(detailEl);
  elTlTooltip.hidden = false;

  const stackRect = elTimelineStack.getBoundingClientRect();
  const anchorRect = anchorEl.getBoundingClientRect();
  const centerX = anchorRect.left - stackRect.left + anchorRect.width / 2;
  const tw = elTlTooltip.offsetWidth || 180;
  const clampedX = Math.max(tw / 2 + 4, Math.min(centerX, stackRect.width - tw / 2 - 4));
  elTlTooltip.style.left = `${clampedX}px`;
}

function showSegmentTooltip(anchorEl, segment) {
  if (!anchorEl || !segment) {
    hideTimelineTooltip();
    return;
  }
  showTimelineInfoTooltip(
    anchorEl,
    formatSegmentTypeLabel(segment),
    `${formatEventTime(segment.t0)} ~ ${formatEventTime(segment.t1)}`,
    `${formatSegmentLabel(segment)} · ${t('segmentDuration')} ${t('segmentDurationFmt', segment.duration)}`,
  );
}

function showSegmentPointTooltip(anchorEl, point) {
  if (!anchorEl || !point) {
    hideTimelineTooltip();
    return;
  }
  showTimelineInfoTooltip(
    anchorEl,
    point.label,
    formatEventTime(point.t),
    t('segmentTitle'),
  );
}

function updateSegmentButtons() {
  const selected = getSelectedSegment();
  const draft = getDraftSegment();
  const hasDraftPoints = Number.isFinite(segmentDraftA) || Number.isFinite(segmentDraftB);
  const hmSegmentOpt = elHmTime?.querySelector('option[value="segment"]');
  if (elSegmentSetA) elSegmentSetA.disabled = !sessionKey;
  if (elSegmentSetB) elSegmentSetB.disabled = !sessionKey;
  if (elSegmentAdd) elSegmentAdd.disabled = !sessionKey || !draft;
  if (elSegmentClear) elSegmentClear.disabled = !selected && !hasDraftPoints;
  if (elSegmentLoop) {
    elSegmentLoop.disabled = !selected;
    elSegmentLoop.checked = loopSelectedSegment;
  }
  if (hmSegmentOpt) hmSegmentOpt.disabled = !selected;
  if (!selected && elHmTime?.value === 'segment') elHmTime.value = 'all';
}

function clearSegmentDraft() {
  segmentDraftA = null;
  segmentDraftB = null;
}

function normalizeDraftPoints() {
  if (!Number.isFinite(segmentDraftA) || !Number.isFinite(segmentDraftB)) return;
  if (segmentDraftA > segmentDraftB) {
    [segmentDraftA, segmentDraftB] = [segmentDraftB, segmentDraftA];
  }
}

function renderDraftPointMarkers() {
  if (!elTlSegmentPoints) return;
  elTlSegmentPoints.innerHTML = '';
  if (duration <= 0) return;

  const points = getDraftPointMarkers();
  if (!points.length) return;

  const fragments = document.createDocumentFragment();
  for (const point of points) {
    const pct = Math.max(0, Math.min(100, (point.t / duration) * 100));
    const marker = document.createElement('button');
    marker.type = 'button';
    marker.className = `timeline-segment-point ${point.role}`;
    marker.style.left = `${pct}%`;
    marker.setAttribute('aria-label', `${point.label} ${formatEventTime(point.t)}`);

    const label = document.createElement('span');
    label.className = 'timeline-segment-point-label';
    label.textContent = point.label;
    const line = document.createElement('span');
    line.className = 'timeline-segment-point-line';
    marker.appendChild(label);
    marker.appendChild(line);

    marker.addEventListener('mouseenter', () => showSegmentPointTooltip(marker, point));
    marker.addEventListener('mouseleave', hideTimelineTooltip);
    marker.addEventListener('focus', () => showSegmentPointTooltip(marker, point));
    marker.addEventListener('blur', hideTimelineTooltip);
    marker.addEventListener('click', () => {
      if (!sessionKey) return;
      hideTimelineTooltip();
      stopPlay();
      setTime(point.t);
      fetchAndRender(currentT);
    });
    fragments.appendChild(marker);
  }
  elTlSegmentPoints.appendChild(fragments);
}

function clearSelectedSegment(options = {}) {
  const {
    rerender = true,
    clearDraft = false,
    refreshHeatmapToo = true,
  } = options;
  selectedSegmentId = null;
  selectedSegmentStats = null;
  segmentStatsPending = false;
  segmentStatsSeq += 1;
  if (clearDraft) clearSegmentDraft();
  loopSelectedSegment = false;
  if (rerender) renderSegments();
  updateSegmentButtons();
  updateSegmentSummary();
  if (refreshHeatmapToo && heatmapEnabled) {
    refreshHeatmap();
  }
}

function renderSegments() {
  hideTimelineTooltip();
  if (elTlSegments) elTlSegments.innerHTML = '';
  if (elTlSegmentPoints) elTlSegmentPoints.innerHTML = '';
  elSegmentList.innerHTML = '';
  renderDraftPointMarkers();

  const segments = getAllSegments();
  const visibleSegments = getVisibleSegments();
  renderSegmentFilterButtons(segments);
  if (!segments.length || duration <= 0) {
    elSegmentList.innerHTML = `<span class="muted" style="font-size:10px">${t('segmentListEmpty')}</span>`;
    updateSegmentButtons();
    return;
  }
  if (!visibleSegments.length) {
    elSegmentList.innerHTML = `<span class="muted" style="font-size:10px">${t('segmentFilteredEmpty')}</span>`;
    updateSegmentButtons();
    return;
  }

  const bandFragments = document.createDocumentFragment();
  const segmentsByKind = new Map();

  for (const segment of visibleSegments) {
    const segClass = segmentKindClass(segment.kind);
    const leftPct = Math.max(0, Math.min(100, (segment.t0 / duration) * 100));
    const widthPct = Math.max(0.2, Math.min(100 - leftPct, ((segment.t1 - segment.t0) / duration) * 100));
    const selected = selectedSegmentId === segment.id;
    const accentColor = segmentAccentColor(segment);

    const band = document.createElement('button');
    band.type = 'button';
    band.className = `timeline-segment ${segClass}${selected ? ' selected' : ''}`;
    band.style.left = `${leftPct}%`;
    band.style.width = `${widthPct}%`;
    band.style.minWidth = '5px';
    band.style.top = `${(SEGMENT_KIND_ROW[segment.kind] ?? 0) * SEGMENT_ROW_STRIDE}px`;
    band.style.borderColor = accentColor;
    band.style.background = `${accentColor}2a`;
    band.setAttribute('aria-label', `${formatSegmentTypeLabel(segment)} ${formatSegmentLabel(segment)}`);
    band.addEventListener('mouseenter', () => showSegmentTooltip(band, segment));
    band.addEventListener('mouseleave', hideTimelineTooltip);
    band.addEventListener('focus', () => showSegmentTooltip(band, segment));
    band.addEventListener('blur', hideTimelineTooltip);
    band.addEventListener('click', () => selectSegment(segment.id, { jump: true }));
    bandFragments.appendChild(band);

    if (!segmentsByKind.has(segment.kind)) segmentsByKind.set(segment.kind, []);
    segmentsByKind.get(segment.kind).push({ segment, selected, accentColor });
  }

  const groupFragments = document.createDocumentFragment();
  for (const kind of SEGMENT_KINDS) {
    const kindItems = segmentsByKind.get(kind);
    if (!kindItems) continue;

    const segClass = segmentKindClass(kind);
    const accentColor = segmentAccentColor({ kind });
    const isCollapsed = collapsedSegmentGroups.has(kind);

    const group = document.createElement('div');
    group.className = `segment-group${isCollapsed ? ' collapsed' : ''}`;

    const header = document.createElement('button');
    header.type = 'button';
    header.className = `segment-group-header ${segClass}`;
    header.style.setProperty('--group-accent', accentColor);
    header.dataset.tipKo = `${formatSegmentTypeLabel(kind)} 그룹 접기/펼치기`;
    header.dataset.tipEn = `Collapse/expand ${formatSegmentTypeLabel(kind)} group`;

    const labelSpan = document.createElement('span');
    labelSpan.className = 'segment-group-label';
    labelSpan.textContent = formatSegmentTypeLabel(kind);

    const countBadge = document.createElement('span');
    countBadge.className = 'segment-group-count';
    countBadge.textContent = String(kindItems.length);

    const arrow = document.createElement('span');
    arrow.className = 'segment-group-arrow';
    arrow.textContent = isCollapsed ? '▶' : '▼';

    header.appendChild(labelSpan);
    header.appendChild(countBadge);
    header.appendChild(arrow);
    header.addEventListener('click', () => {
      if (collapsedSegmentGroups.has(kind)) collapsedSegmentGroups.delete(kind);
      else collapsedSegmentGroups.add(kind);
      renderSegments();
    });

    const chipList = document.createElement('div');
    chipList.className = 'segment-group-chips';

    for (const { segment, selected: sel, accentColor: ac } of kindItems) {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = `segment-chip ${segmentKindClass(segment.kind)}${sel ? ' selected' : ''}`;
      chip.dataset.segmentId = segment.id;
      chip.style.borderColor = ac;
      chip.dataset.tipKo = `${segment.t0.toFixed(1)}s — ${formatSegmentLabel(segment)} (클릭하여 선택)`;
      chip.dataset.tipEn = `${segment.t0.toFixed(1)}s — ${formatSegmentLabel(segment)} (click to select)`;
      const timeSpan = document.createElement('span');
      timeSpan.className = 'bookmark-time';
      timeSpan.textContent = `${segment.t0.toFixed(1)}s`;
      const textSpan = document.createElement('span');
      textSpan.className = 'segment-chip-label';
      textSpan.textContent = formatSegmentLabel(segment);
      chip.appendChild(timeSpan);
      chip.appendChild(textSpan);
      if (segment.kind === 'setplay_span' && segment.post_possession != null) {
        const ppDot = document.createElement('span');
        ppDot.className = `segment-post-poss-dot ${segment.post_possession}`;
        const ppLabel = {
          our:   t('setplayPostPossOur'),
          enemy: t('setplayPostPossEnemy'),
          loose: t('setplayPostPossLoose'),
        }[segment.post_possession] ?? '';
        ppDot.title = `${t('setplayPostPoss')}: ${ppLabel}`;
        chip.appendChild(ppDot);
      }
      if (segment.kind === 'custom' && !segment.draft) {
        const editBtn = document.createElement('button');
        editBtn.type = 'button';
        editBtn.className = 'segment-chip-edit';
        editBtn.textContent = '✎';
        editBtn.title = lang === 'ko' ? '이름 변경' : 'Rename';
        editBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          startSegmentRename(segment.id, textSpan);
        });
        chip.appendChild(editBtn);
      }
      chip.addEventListener('click', () => selectSegment(segment.id, { jump: true }));
      chipList.appendChild(chip);
    }

    group.appendChild(header);
    group.appendChild(chipList);
    groupFragments.appendChild(group);
  }

  if (elTlSegments) elTlSegments.appendChild(bandFragments);
  elSegmentList.appendChild(groupFragments);
  updateSegmentButtons();
}

function resetSegments() {
  segmentPresets = [];
  customSegments = [];
  customSegmentCounter = 0;
  visibleSegmentKinds.clear();
  for (const kind of SEGMENT_KINDS) visibleSegmentKinds.add(kind);
  collapsedSegmentGroups.clear();
  for (const kind of SEGMENT_KINDS) collapsedSegmentGroups.add(kind);
  clearSelectedSegment({
    rerender: false,
    clearDraft: true,
    refreshHeatmapToo: false,
  });
  renderSegments();
}

function renderRobotGaps() {
  if (!elTlGaps || !elTimelineStack) return;
  elTlGaps.innerHTML = '';
  const GAP_ROW_H = 5;
  const n = robotIds.length;
  elTimelineStack.style.paddingTop = n > 0 ? `${56 + n * GAP_ROW_H}px` : '56px';
  if (!duration || !n) return;

  const frag = document.createDocumentFragment();
  for (const rid of robotIds) {
    const color = court.robotColor(rid);
    const gaps = robotGaps[String(rid)] || [];

    const row = document.createElement('div');
    row.className = 'tl-gap-row';

    const bg = document.createElement('div');
    bg.className = 'tl-gap-row-bg';
    bg.style.background = color;
    row.appendChild(bg);

    for (const [g0, g1] of gaps) {
      const leftPct = Math.max(0, Math.min(100, (g0 / duration) * 100));
      const widthPct = Math.max(0.3, Math.min(100 - leftPct, ((g1 - g0) / duration) * 100));
      const miss = document.createElement('div');
      miss.className = 'tl-gap-miss';
      miss.style.left = `${leftPct}%`;
      miss.style.width = `${widthPct}%`;
      const durStr = (g1 - g0).toFixed(1);
      miss.addEventListener('mouseenter', () => showTimelineInfoTooltip(
        miss,
        lang === 'ko' ? `R${rid} 데이터 없음` : `R${rid} no data`,
        `${g0.toFixed(1)}s – ${g1.toFixed(1)}s`,
        lang === 'ko' ? `공백 ${durStr}s` : `gap ${durStr}s`,
      ));
      miss.addEventListener('mouseleave', hideTimelineTooltip);
      row.appendChild(miss);
    }

    frag.appendChild(row);
  }
  elTlGaps.appendChild(frag);
}

function selectSegment(segmentId, options = {}) {
  const { jump = false } = options;
  const segment = getSegmentById(segmentId);
  const visibleSegment = segment && visibleSegmentKinds.has(segment.kind) ? segment : null;
  selectedSegmentId = visibleSegment ? visibleSegment.id : null;
  selectedSegmentStats = null;
  segmentStatsPending = !!visibleSegment;
  segmentStatsSeq += 1;
  renderSegments();
  updateSegmentButtons();
  updateSegmentSummary();
  if (visibleSegment) {
    refreshSelectedSegmentStats();
    if (jump) {
      stopPlay();
      setTime(visibleSegment.t0);
      fetchAndRender(currentT);
    }
  }
  if (heatmapEnabled) {
    refreshHeatmap();
  }
}

function setSpaceBar(ourEl, enemyEl, ourPct, enemyPct, valid) {
  const our = valid ? Math.max(0, Math.min(100, ourPct)) : 0;
  const enemy = valid ? Math.max(0, Math.min(100, enemyPct)) : 0;
  ourEl.style.width = `${our}%`;
  enemyEl.style.width = `${enemy}%`;
  ourEl.style.opacity = valid ? '1' : '0.2';
  enemyEl.style.opacity = valid ? '1' : '0.2';
}

// ── Game summary panel ────────────────────────────────────────────────────────
// State codes: 0=loose, 1=our, 2=enemy, 3=stuck
const _POSS_FILL = [
  'rgba(100,116,139,0.45)',  // loose
  'rgba(59,130,246,0.78)',   // our
  'rgba(220,38,38,0.68)',    // enemy
  'rgba(234,179,8,0.72)',    // stuck
];
const _POSS_TL_W = 220, _POSS_TL_H = 28, _POSS_TL_PX = 12, _POSS_TL_PY = 4;

function buildPossessionTimelineSVG() {
  if (!possPreload?.samples?.length) return '';
  const samples = possPreload.samples;
  const W = _POSS_TL_W, H = _POSS_TL_H, PX = _POSS_TL_PX, PY = _POSS_TL_PY;
  const iW = W - PX * 2, iH = H - PY * 2;
  const safeDur = Math.max(duration, 0.001);
  const toX = t_ => PX + (t_ / safeDur) * iW;

  let rects = '';
  for (let i = 0; i < samples.length; i++) {
    const [t0, st] = samples[i];
    const t1 = i + 1 < samples.length ? samples[i + 1][0] : safeDur;
    const x0 = toX(t0), x1 = toX(t1);
    rects += `<rect x="${x0.toFixed(1)}" y="${PY}" width="${Math.max(0.5, x1 - x0).toFixed(1)}" height="${iH}" fill="${_POSS_FILL[st] ?? _POSS_FILL[0]}"/>`;
  }

  let halfLine = '';
  if (possPreload.half_split != null) {
    const hx = toX(possPreload.half_split).toFixed(1);
    halfLine = `<line x1="${hx}" y1="${PY}" x2="${hx}" y2="${H - PY}" stroke="rgba(255,255,255,0.4)" stroke-width="0.8"/>`;
  }

  const mx = toX(currentT).toFixed(1);
  return `<svg class="poss-timeline-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" data-tip-ko="클릭하면 확대 창으로 볼 수 있습니다" data-tip-en="Click to open in enlarged popup">
    <rect x="${PX}" y="${PY}" width="${iW}" height="${iH}" rx="2" fill="rgba(0,0,0,0.18)"/>
    ${rects}${halfLine}
    <line class="poss-timeline-marker" x1="${mx}" y1="${PY - 1}" x2="${mx}" y2="${H - PY + 1}" stroke="rgba(248,250,252,0.9)" stroke-width="0.8" stroke-dasharray="3 2"/>
  </svg>`;
}

function updatePossessionTimelineMarker(t_) {
  if (!possPreload?.samples?.length) return;
  const iW = _POSS_TL_W - _POSS_TL_PX * 2;
  const safeDur = Math.max(duration, 0.001);
  const x = (_POSS_TL_PX + (t_ / safeDur) * iW).toFixed(1);
  document.querySelectorAll('line.poss-timeline-marker').forEach(el => {
    el.setAttribute('x1', x);
    el.setAttribute('x2', x);
  });
}

function renderSpacingBlock(sp) {
  if (!sp) return '';
  const cx = sp.centroid_x ?? 0;
  const cxLabel = cx >= 0 ? `+${cx.toFixed(2)}m` : `${cx.toFixed(2)}m`;
  return `<div class="spacing-block">
    <div class="spacing-row">
      <span title="${t('formationTipCentroid')}">${t('segmentStatsSpacingCentroid')}</span>
      <strong>${cxLabel}</strong>
    </div>
    <div class="spacing-row">
      <span title="${t('formationTipWidth')}">${t('segmentStatsSpacingWidth')}</span>
      <strong>${(sp.width ?? 0).toFixed(1)}m / ${(sp.depth ?? 0).toFixed(1)}m</strong>
    </div>
    <div class="spacing-row">
      <span title="${t('formationTipAvgDist')}">${t('segmentStatsSpacingDist')}</span>
      <strong>${(sp.avg_dist ?? 0).toFixed(1)}m</strong>
    </div>
    <div class="spacing-row">
      <span title="${t('formationTipFwd')}">${t('segmentStatsSpacingFwd')}</span>
      <strong>${(sp.fwd_count ?? 0).toFixed(1)} / ${sp.robot_count ?? 0}</strong>
    </div>
  </div>`;
}

function renderPossessionBlock(possession) {
  if (!possession || !possession.available) return '';
  const hasEnemy = possession.enemy_tracked;
  const ourPct   = possession.our_pct;   // keep null; used with ?? 0 in bar widths
  const enemyPct = possession.enemy_pct ?? 0;
  const loosePct = possession.loose_pct;

  const stuckPct = possession.stuck_pct ?? 0;
  const ourTip   = t('possessionTipOur');
  const enemyTip = t('possessionTipEnemy');
  const stuckTip = t('possessionTipStuck');
  const looseTip = t('possessionTipLoose');
  const lostTip  = t('possessionTipLost');
  const gainedTip= t('possessionTipGained');
  const zoneTip  = t('possessionTipZone');

  let barHtml;
  if (hasEnemy) {
    barHtml = `
      <div class="possession-bar">
        <div class="possession-bar-seg our"   style="width:${ourPct ?? 0}%"   title="${ourTip}"></div>
        <div class="possession-bar-seg stuck" style="width:${stuckPct}%" title="${stuckTip}"></div>
        <div class="possession-bar-seg enemy" style="width:${enemyPct}%" title="${enemyTip}"></div>
      </div>
      <div class="possession-bar-labels">
        <span title="${ourTip}">${t('possessionOur')} <strong>${ourPct ?? 0}%</strong></span>
        <span title="${stuckTip}" class="poss-label-stuck">${t('possessionStuck')} <strong>${stuckPct}%</strong></span>
        <span title="${enemyTip}">${t('possessionEnemy')} <strong>${enemyPct}%</strong></span>
      </div>`;
  } else if (ourPct !== null) {
    // Solo mode: show our-vs-loose bar even without enemy data
    const looseSoloPct = loosePct ?? (100 - ourPct);
    barHtml = `
      <div class="possession-bar">
        <div class="possession-bar-seg our"        style="width:${ourPct}%"        title="${ourTip}"></div>
        <div class="possession-bar-seg loose-solo" style="width:${looseSoloPct.toFixed(1)}%" title="${looseTip}"></div>
      </div>
      <div class="possession-bar-labels solo">
        <span title="${ourTip}">${t('possessionOur')} <strong>${ourPct}%</strong></span>
        <span title="${looseTip}">${t('possessionLoose')} <strong>${looseSoloPct.toFixed(1)}%</strong></span>
      </div>
      <div class="muted" style="font-size:9px;margin-top:1px">${t('possessionNoEnemy')}</div>`;
  } else {
    barHtml = `<div class="muted" style="font-size:10px">${t('possessionNoEnemy')}</div>`;
  }

  const metaParts = [];
  if (loosePct !== null && hasEnemy)
    metaParts.push(`<span title="${looseTip}">${t('possessionLoose')} ${loosePct}%</span>`);
  if (hasEnemy)
    metaParts.push(
      `<span title="${lostTip}">${t('possessionTurnoverLost')} ${possession.turnovers_lost}</span>` +
      ` · ` +
      `<span title="${gainedTip}">${t('possessionTurnoverGained')} ${possession.turnovers_gained}</span>`
    );
  const metaHtml = metaParts.length
    ? `<div class="possession-meta">${metaParts.join(' &nbsp;|&nbsp; ')}</div>` : '';

  const bz = possession.ball_zone;
  const zf = possession.ball_zone_flow;
  const zfTip = t('possZoneFlowTip');
  const zfChips = zf ? (() => {
    const pairs = [
      [t('possZoneFlowLM'), (zf.left_to_mid  || 0) + (zf.mid_to_left  || 0)],
      [t('possZoneFlowMR'), (zf.mid_to_right || 0) + (zf.right_to_mid || 0)],
      [t('possZoneFlowLR'), (zf.left_to_right|| 0) + (zf.right_to_left|| 0)],
    ].filter(([, n]) => n > 0);
    return pairs.length
      ? `<div class="ball-zone-flow" title="${zfTip}">${pairs.map(([lbl, n]) => `<span class="zone-flow-chip">${lbl} ${n}</span>`).join('')}</div>`
      : '';
  })() : '';

  const zoneHtml = bz ? `
    <div class="possession-zone-label" title="${zoneTip}">${t('possessionBallZone')}</div>
    <div class="possession-zone-bar" title="${zoneTip}">
      <div class="possession-zone-seg left"  style="width:${bz.left_pct}%"  title="${t('possessionZoneLeft')} ${bz.left_pct}%"></div>
      <div class="possession-zone-seg mid"   style="width:${bz.mid_pct}%"   title="${t('possessionZoneMid')} ${bz.mid_pct}%"></div>
      <div class="possession-zone-seg right" style="width:${bz.right_pct}%" title="${t('possessionZoneRight')} ${bz.right_pct}%"></div>
    </div>
    <div class="possession-zone-pcts">
      <span title="${t('possessionZoneLeft')}">${bz.left_pct}%</span>
      <span title="${t('possessionZoneMid')}">${bz.mid_pct}%</span>
      <span title="${t('possessionZoneRight')}">${bz.right_pct}%</span>
    </div>${zfChips}` : '';

  const tlSvg = buildPossessionTimelineSVG();
  const timelineHtml = tlSvg
    ? `<div class="poss-timeline-label">${t('possTimelineTitle')}</div>${tlSvg}`
    : '';

  return `<div class="possession-block">
    <div class="possession-title">${t('possessionTitle')}</div>
    ${barHtml}${metaHtml}${zoneHtml}${timelineHtml}
  </div>`;
}

function renderGameSummary() {
  if (_popupSvgEl?.classList.contains('poss-timeline-svg')) closeChartPopup();
  const elSection      = $('summary-section');
  const elTeam         = $('summary-team');
  const elBreakdown    = $('summary-robot-breakdown');
  const elSummaryTabs  = $('summary-tabs');
  if (!elSection || !elTeam || !elBreakdown) return;

  if (!gameSummary) {
    elSection.hidden = true;
    return;
  }
  elSection.hidden = false;

  const hasHalves = gameSummary.half_split !== null
                 && gameSummary.first_half !== null
                 && gameSummary.second_half !== null;

  // Tab visibility & active state
  elSummaryTabs?.querySelectorAll('.summary-tab').forEach(tab => {
    const half = tab.dataset.half;
    if (half !== 'full') tab.hidden = !hasHalves;
    tab.classList.toggle('active', half === summaryHalf);
  });
  if (!hasHalves && summaryHalf !== 'full') summaryHalf = 'full';

  const stats = summaryHalf === 'first'  ? gameSummary.first_half
              : summaryHalf === 'second' ? gameSummary.second_half
              : gameSummary.full_game;
  if (!stats) { elTeam.innerHTML = ''; elBreakdown.innerHTML = ''; return; }

  // Duration formatting
  const dur    = stats.duration ?? 0;
  const durMin = Math.floor(dur / 60);
  const durSec = Math.floor(dur % 60);
  const durStr = `${durMin}:${String(durSec).padStart(2, '0')}`;

  // Team overview rows
  elTeam.innerHTML = `
    <div class="segment-metric-row"><span>${t('summaryDuration')}</span><strong>${durStr}</strong></div>
    <div class="segment-metric-row"><span>${t('summaryActiveRobots')}</span><strong>${stats.active_robot_count} / ${stats.robot_count}</strong></div>
    <div class="segment-metric-row"><span>${t('summaryTotalDist')}</span><strong>${t('summaryDistFmt', stats.total_distance_m)}</strong></div>
    <div class="segment-metric-row"><span>${t('summaryTotalKicks')}</span><strong>${stats.total_kick_count}</strong></div>
    <div class="segment-metric-row"><span>${t('summaryTotalFalls')}</span><strong>${stats.total_fall_count}</strong></div>
    <div class="segment-metric-row"><span>${t('summaryMaxSpeed')}</span><strong>${t('summarySpeedFmt', stats.max_robot_speed_mps)}</strong></div>
    ${renderPossessionBlock(stats.possession)}
  `;

  // Per-robot breakdown
  elBreakdown.innerHTML = '';
  for (const rstat of (stats.robot_stats || [])) {
    if (!rstat.has_pose_data && rstat.kick_count === 0 && rstat.fall_count === 0) continue;
    const color = court.robotColor(rstat.robot_id);
    const card  = document.createElement('div');
    card.className = 'summary-robot-card';
    const fallChip  = rstat.fall_count > 0
      ? `<span class="summary-stat-chip fall">↓ ${rstat.fall_count}</span>` : '';
    const destChip  = (rstat.dest_change_count ?? 0) > 0
      ? `<span class="summary-stat-chip">→ ${rstat.dest_change_count}</span>` : '';
    card.innerHTML = `
      <div class="summary-robot-head">
        <span class="summary-robot-name">
          <span class="summary-robot-dot" style="background:${color}"></span>R${rstat.robot_id}
        </span>
        <span class="summary-robot-dist">${t('summaryDistFmt', rstat.distance_m)}</span>
      </div>
      <div class="summary-robot-stats">
        <span class="summary-stat-chip">⚡ ${t('summarySpeedFmt', rstat.max_speed_mps)}</span>
        <span class="summary-stat-chip">⚽ ${rstat.kick_count}</span>
        ${fallChip}${destChip}
      </div>`;
    elBreakdown.appendChild(card);
  }
}

function resetSpaceControlPanel() {
  closeChartPopup();
  scSamplesPreload = null;
  scTimeline = [];
  spacingTimeline = null;
  if (elFormationSection) elFormationSection.hidden = true;
  if (elFormationChartBlock) elFormationChartBlock.hidden = true;
  elScEmpty.hidden = false;
  elScContent.hidden = true;
  elScCurrentText.textContent = '—';
  elScAverageText.textContent = '—';
  setSpaceBar(elScCurrentOur, elScCurrentEnemy, 0, 0, false);
  setSpaceBar(elScAverageOur, elScAverageEnemy, 0, 0, false);
  elScChart.innerHTML = '';
  elScBreakdown.innerHTML = '';
}

// ── Team Formation / Spacing ──────────────────────────────────────────────────
function computeFormation(robots) {
  const pts = (robots || []).filter(r => r.x != null && r.y != null);
  const n = pts.length;
  if (n < 1) return null;
  const xs = pts.map(r => r.x), ys = pts.map(r => r.y);
  const cx = xs.reduce((s, v) => s + v, 0) / n;
  const cy = ys.reduce((s, v) => s + v, 0) / n;
  const width = n >= 2 ? Math.max(...xs) - Math.min(...xs) : 0;
  const depth = n >= 2 ? Math.max(...ys) - Math.min(...ys) : 0;
  let avgDist = 0;
  if (n >= 2) {
    let sum = 0, cnt = 0;
    for (let i = 0; i < n; i++)
      for (let j = i + 1; j < n; j++) {
        sum += Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y);
        cnt++;
      }
    avgDist = sum / cnt;
  }
  return {
    n,
    centroid_x: Math.round(cx * 100) / 100,
    centroid_y: Math.round(cy * 100) / 100,
    width:      Math.round(width * 100) / 100,
    depth:      Math.round(depth * 100) / 100,
    avg_dist:   Math.round(avgDist * 100) / 100,
    fwd_count:  pts.filter(r => r.x > 0).length,
  };
}

function buildSpacingTimeline() {
  if (!scSamplesPreload?.samples?.length) { spacingTimeline = null; return; }
  spacingTimeline = scSamplesPreload.samples
    .map(s => { const f = computeFormation(s.robots); return f ? { t: s.t, ...f } : null; })
    .filter(Boolean);
  renderFormationChart();
}

// SVG chart: centroid_x trend (attack/defense balance)
function renderFormationChart() {
  if (!elFormationChart || !spacingTimeline?.length) {
    if (elFormationChartBlock) elFormationChartBlock.hidden = true;
    return;
  }
  const W = 220, H = 44, PX = 12, PY = 5;
  const iW = W - PX * 2, iH = H - PY * 2;
  const safeDur = Math.max(duration, 0.001);
  const toX = t_ => PX + (t_ / safeDur) * iW;

  const vals = spacingTimeline.map(s => s.centroid_x);
  const minV = Math.min(-1, ...vals), maxV = Math.max(1, ...vals);
  const rangeV = maxV - minV || 1;
  const toY = v => PY + iH - ((v - minV) / rangeV) * iH;

  const zeroY = toY(0).toFixed(1);
  let svg = `<rect x="${PX}" y="${PY}" width="${iW}" height="${iH}" rx="2" fill="rgba(0,0,0,0.18)"/>`;
  // Zero line (field center)
  svg += `<line x1="${PX}" y1="${zeroY}" x2="${PX + iW}" y2="${zeroY}" stroke="rgba(255,255,255,0.18)" stroke-width="1" stroke-dasharray="3 2"/>`;

  // Area fill
  const pts = spacingTimeline.map(s => `${toX(s.t).toFixed(1)},${toY(s.centroid_x).toFixed(1)}`).join(' ');
  const firstX = toX(spacingTimeline[0].t).toFixed(1);
  const lastX  = toX(spacingTimeline[spacingTimeline.length - 1].t).toFixed(1);
  svg += `<polyline points="${pts}" fill="none" stroke="rgba(96,165,250,0.75)" stroke-width="0.7" stroke-linejoin="round"/>`;
  svg += `<polygon points="${firstX},${PY + iH} ${pts} ${lastX},${PY + iH}" fill="rgba(96,165,250,0.12)"/>`;

  // Attack half label
  svg += `<text x="${PX + 2}" y="${PY + 8}" font-size="7" fill="rgba(255,255,255,0.30)">${t('formationAttack')}</text>`;
  svg += `<text x="${PX + 2}" y="${PY + iH - 2}" font-size="7" fill="rgba(255,255,255,0.30)">${t('formationDefend')}</text>`;

  // Playback cursor
  const mx = toX(currentT).toFixed(1);
  svg += `<line class="formation-chart-marker" x1="${mx}" y1="${PY - 1}" x2="${mx}" y2="${H - PY + 1}" stroke="rgba(248,250,252,0.85)" stroke-width="0.8" stroke-dasharray="3 2"/>`;

  elFormationChart.innerHTML = svg;
  elFormationChartBlock.hidden = false;
}

function updateFormationChartMarker(t_) {
  if (!spacingTimeline?.length || !elFormationChart) return;
  const iW = 220 - 12 * 2;
  const x = (12 + (t_ / Math.max(duration, 0.001)) * iW).toFixed(1);
  elFormationChart.querySelectorAll('line.formation-chart-marker').forEach(el => {
    el.setAttribute('x1', x); el.setAttribute('x2', x);
  });
}

function renderFormationPanel(formation) {
  if (!elFormationSection || !elFormationRealtime) return;
  if (!formation) {
    elFormationSection.hidden = true;
    return;
  }
  elFormationSection.hidden = false;

  const cx = formation.centroid_x ?? 0;
  const cxDir = cx > 0.2
    ? `<span class="form-tag attack">${t('formationAttack')}</span>`
    : cx < -0.2
      ? `<span class="form-tag defend">${t('formationDefend')}</span>`
      : '';

  elFormationRealtime.innerHTML = `
    <div class="formation-metrics">
      <div class="form-row" title="${t('formationTipCentroid')}">
        <span class="form-label">${t('formationCentroid')}</span>
        <span class="form-val">${cx >= 0 ? '+' : ''}${cx.toFixed(2)}m ${cxDir}</span>
      </div>
      <div class="form-row" title="${t('formationTipWidth')}">
        <span class="form-label">${t('formationWidth')}</span>
        <span class="form-val">${(formation.width ?? 0).toFixed(1)}m</span>
        <span class="form-label" style="margin-left:8px" title="${t('formationTipDepth')}">${t('formationDepth')}</span>
        <span class="form-val">${(formation.depth ?? 0).toFixed(1)}m</span>
      </div>
      <div class="form-row" title="${t('formationTipAvgDist')}">
        <span class="form-label">${t('formationAvgDist')}</span>
        <span class="form-val">${(formation.avg_dist ?? 0).toFixed(1)}m</span>
        <span class="form-label" style="margin-left:8px" title="${t('formationTipFwd')}">${t('formationFwd')}</span>
        <span class="form-val">${formation.fwd_count ?? 0} / ${formation.n ?? 0}</span>
      </div>
    </div>`;
}

function buildSpaceControlTimeline() {
  scTimeline = (scSamplesPreload?.samples || []).map(sample => {
    const stats = court.analyzeSpaceControl(sample, { requireBothTeams: true });
    return {
      t: sample.t,
      valid: !!stats?.valid,
      ourPct: stats?.ourPct ?? null,
      enemyPct: stats?.enemyPct ?? null,
    };
  });
  updateSegmentSummary();
}

function getSpaceControlAverageAt(t_) {
  const samples = scTimeline.filter(s => s.valid && s.t <= t_ + 1e-6);
  if (!samples.length) return null;
  const ourPct = samples.reduce((sum, s) => sum + s.ourPct, 0) / samples.length;
  return { ourPct, enemyPct: 100 - ourPct };
}

function getSpaceControlAverageForRange(t0, t1) {
  const samples = scTimeline.filter(
    s => s.valid && s.t >= t0 - 1e-6 && s.t <= t1 + 1e-6,
  );
  if (!samples.length) return null;
  const ourPct = samples.reduce((sum, s) => sum + s.ourPct, 0) / samples.length;
  return { ourPct, enemyPct: 100 - ourPct };
}

function getNearestSpaceControlSampleAt(t_) {
  const valid = scTimeline.filter(s => s.valid);
  if (!valid.length) return null;
  return valid.reduce((best, sample) => (
    Math.abs(sample.t - t_) < Math.abs(best.t - t_) ? sample : best
  ), valid[0]);
}

function renderSpaceControlChart() {
  const valid = scTimeline.filter(s => s.valid);
  if (!valid.length) {
    elScChart.innerHTML = '';
    return;
  }

  const W = 220;
  const H = 80;
  const PAD_X = 12;
  const PAD_Y = 8;
  const innerW = W - PAD_X * 2;
  const innerH = H - PAD_Y * 2;
  const safeDuration = Math.max(duration, valid[valid.length - 1].t, 0.001);
  const toX = (t_) => PAD_X + (t_ / safeDuration) * innerW;
  const toY = (pct) => PAD_Y + (1 - pct / 100) * innerH;
  const linePoints = valid.map(s => [toX(s.t), toY(s.ourPct)]);
  const linePath = linePoints.map(([x, y], idx) => `${idx ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
  const baseY = PAD_Y + innerH;
  const topY = PAD_Y;
  const linePathForFill = linePath.replace(/^M/, 'L');
  const fillOur = `M${linePoints[0][0].toFixed(2)},${baseY.toFixed(2)} ${linePathForFill} L${linePoints[linePoints.length - 1][0].toFixed(2)},${baseY.toFixed(2)} Z`;
  const fillEnemy = `M${linePoints[0][0].toFixed(2)},${topY.toFixed(2)} ${linePathForFill} L${linePoints[linePoints.length - 1][0].toFixed(2)},${topY.toFixed(2)} Z`;
  const markerX = toX(Math.max(0, Math.min(currentT, safeDuration))).toFixed(2);
  const currentSample = getNearestSpaceControlSampleAt(currentT);
  const currentDot = currentSample
    ? `<circle cx="${toX(currentSample.t).toFixed(2)}" cy="${toY(currentSample.ourPct).toFixed(2)}" r="2.8" fill="#f8fafc"/>`
    : '';

  elScChart.innerHTML = `
    <line x1="${PAD_X}" y1="${topY}" x2="${W - PAD_X}" y2="${topY}" stroke="rgba(255,255,255,0.12)" stroke-width="0.6"/>
    <line x1="${PAD_X}" y1="${toY(50).toFixed(2)}" x2="${W - PAD_X}" y2="${toY(50).toFixed(2)}" stroke="rgba(255,255,255,0.16)" stroke-width="0.6" stroke-dasharray="4 4"/>
    <line x1="${PAD_X}" y1="${baseY}" x2="${W - PAD_X}" y2="${baseY}" stroke="rgba(255,255,255,0.12)" stroke-width="0.6"/>
    <path d="${fillEnemy}" fill="rgba(220,38,38,0.18)"/>
    <path d="${fillOur}" fill="rgba(59,130,246,0.22)"/>
    <path d="${linePath}" fill="none" stroke="rgba(255,255,255,0.86)" stroke-width="1.0" stroke-linejoin="round" stroke-linecap="round"/>
    <line x1="${markerX}" y1="${topY}" x2="${markerX}" y2="${baseY}" stroke="rgba(248,250,252,0.5)" stroke-width="0.7" stroke-dasharray="3 3"/>
    ${currentDot}
    <text x="2" y="${topY + 4}" font-size="8" fill="rgba(255,255,255,0.42)">100</text>
    <text x="2" y="${toY(50).toFixed(2)}" font-size="8" fill="rgba(255,255,255,0.42)" dominant-baseline="middle">50</text>
    <text x="6" y="${baseY}" font-size="8" fill="rgba(255,255,255,0.42)" dominant-baseline="ideographic">0</text>
  `;
}

function renderSpaceControlBreakdown(stats) {
  if (!stats?.valid) {
    elScBreakdown.innerHTML = `<div class="muted" style="font-size:10px">${t('spaceControlUnavailable')}</div>`;
    return;
  }

  const rows = stats.sites
    .filter(site => site.team === 'our')
    .sort((a, b) => b.area - a.area)
    .map(site => `
      <div class="space-breakdown-row">
        <div class="space-breakdown-head">
          <span class="space-breakdown-left">
            <span class="space-breakdown-chip" style="background:${site.color}"></span>
            <span>${site.label}</span>
          </span>
          <span>${site.pct.toFixed(1)}%</span>
        </div>
        <div class="space-breakdown-bar">
          <div class="space-breakdown-fill" style="width:${site.pct.toFixed(1)}%; background:${site.color}"></div>
        </div>
      </div>
    `)
    .join('');

  elScBreakdown.innerHTML = rows || `<div class="muted" style="font-size:10px">${t('spaceControlUnavailable')}</div>`;
}

function updateSpaceControlPanel(frame) {
  const currentStats = court.analyzeSpaceControl(frame, { requireBothTeams: true });
  const averageStats = getSpaceControlAverageAt(currentT);
  const hasAnyData = !!currentStats?.valid || scTimeline.some(s => s.valid);

  elScEmpty.hidden = hasAnyData;
  elScContent.hidden = !hasAnyData;
  if (!hasAnyData) {
    setSpaceBar(elScCurrentOur, elScCurrentEnemy, 0, 0, false);
    setSpaceBar(elScAverageOur, elScAverageEnemy, 0, 0, false);
    elScCurrentText.textContent = '—';
    elScAverageText.textContent = '—';
    elScChart.innerHTML = '';
    elScBreakdown.innerHTML = '';
    return;
  }

  if (currentStats?.valid) {
    elScCurrentText.textContent = t('spaceControlCurrentFmt', currentStats.ourPct, currentStats.enemyPct);
    setSpaceBar(elScCurrentOur, elScCurrentEnemy, currentStats.ourPct, currentStats.enemyPct, true);
  } else {
    elScCurrentText.textContent = t('spaceControlUnavailable');
    setSpaceBar(elScCurrentOur, elScCurrentEnemy, 0, 0, false);
  }

  if (averageStats) {
    elScAverageText.textContent = t('spaceControlAverageFmt', averageStats.ourPct, averageStats.enemyPct);
    setSpaceBar(elScAverageOur, elScAverageEnemy, averageStats.ourPct, averageStats.enemyPct, true);
  } else {
    elScAverageText.textContent = t('spaceControlUnavailable');
    setSpaceBar(elScAverageOur, elScAverageEnemy, 0, 0, false);
  }

  renderSpaceControlChart();
  renderSpaceControlBreakdown(currentStats);
}

function formatDistanceMeters(v) {
  return `${Number(v || 0).toFixed(1)}m`;
}

function formatSpeedMps(v) {
  return `${Number(v || 0).toFixed(2)}m/s`;
}

function updateSegmentSummary() {
  const segment = getSelectedSegment();
  if (!segment) {
    elSegmentEmpty.hidden = false;
    elSegmentContent.hidden = true;
    elSegmentName.textContent = '—';
    elSegmentRange.textContent = '—';
    elSegmentBadges.innerHTML = '';
    elSegmentOverview.innerHTML = '';
    elSegmentRobotBreakdown.innerHTML = '';
    return;
  }

  elSegmentEmpty.hidden = true;
  elSegmentContent.hidden = false;
  elSegmentName.textContent = formatSegmentLabel(segment);
  elSegmentRange.textContent = `${formatEventTime(segment.t0)} ~ ${formatEventTime(segment.t1)}`;
  const ppLabel = segment.kind === 'setplay_span' && segment.post_possession != null
    ? ({ our: t('setplayPostPossOur'), enemy: t('setplayPostPossEnemy'), loose: t('setplayPostPossLoose') }[segment.post_possession] ?? '')
    : null;
  elSegmentBadges.innerHTML = `
    <span class="segment-badge"><span class="muted">${formatSegmentTypeLabel(segment)}</span></span>
    <span class="segment-badge"><span class="muted">${t('segmentDuration')}</span> <strong>${t('segmentDurationFmt', segment.duration)}</strong></span>
    ${ppLabel != null ? `<span class="segment-badge segment-post-poss-dot ${segment.post_possession}" style="width:auto;height:auto;border-radius:4px;padding:2px 6px;font-size:9px">${t('setplayPostPoss')}: <strong>${ppLabel}</strong></span>` : ''}
  `;

  if (segmentStatsPending && !selectedSegmentStats) {
    elSegmentOverview.innerHTML = `<div class="muted" style="font-size:10px">${t('segmentStatsLoading')}</div>`;
    elSegmentRobotBreakdown.innerHTML = '';
    return;
  }

  if (!selectedSegmentStats) {
    elSegmentOverview.innerHTML = `<div class="muted" style="font-size:10px">${t('segmentStatsUnavailable')}</div>`;
    elSegmentRobotBreakdown.innerHTML = '';
    return;
  }

  const spaceAvg = getSpaceControlAverageForRange(segment.t0, segment.t1);
  elSegmentOverview.innerHTML = `
    <div class="segment-metric-row"><span>${t('segmentStatsRobots')}</span><strong>${selectedSegmentStats.active_robot_count} / ${selectedSegmentStats.robot_count}</strong></div>
    <div class="segment-metric-row"><span>${t('segmentStatsDistance')}</span><strong>${formatDistanceMeters(selectedSegmentStats.total_distance_m)}</strong></div>
    <div class="segment-metric-row"><span>${t('segmentStatsKicks')}</span><strong>${selectedSegmentStats.total_kick_count}</strong></div>
    <div class="segment-metric-row"><span>${t('segmentStatsFalls')}</span><strong>${selectedSegmentStats.total_fall_count}</strong></div>
    <div class="segment-metric-row"><span>${t('segmentStatsMaxSpeed')}</span><strong>${formatSpeedMps(selectedSegmentStats.max_robot_speed_mps)}</strong></div>
    <div class="segment-metric-row"><span>${t('segmentStatsSpaceAvg')}</span><strong>${spaceAvg ? t('segmentSpaceAvgFmt', spaceAvg.ourPct, spaceAvg.enemyPct) : '—'}</strong></div>
    ${renderSpacingBlock(selectedSegmentStats.team_spacing)}
    ${renderPossessionBlock(selectedSegmentStats.possession)}
  `;

  const robotRows = (selectedSegmentStats.robot_stats || [])
    .filter(stat => stat.has_pose_data || stat.kick_count > 0 || stat.fall_count > 0)
    .sort((a, b) => (
      (b.distance_m - a.distance_m) ||
      (b.kick_count - a.kick_count) ||
      (a.robot_id - b.robot_id)
    ));
  if (!robotRows.length) {
    elSegmentRobotBreakdown.innerHTML = `<div class="muted" style="font-size:10px">${t('segmentStatsUnavailable')}</div>`;
    return;
  }

  elSegmentRobotBreakdown.innerHTML = robotRows.map(stat => `
    <div class="segment-robot-card">
      <div class="segment-robot-head">
        <span class="segment-robot-name">
          <span class="segment-robot-dot" style="background:${court.robotColor(stat.robot_id)}"></span>
          <span>${t('robotLabel', stat.robot_id)}</span>
        </span>
        <span>${formatDistanceMeters(stat.distance_m)}</span>
      </div>
      <div class="segment-metric-row"><span>${t('segmentStatsMaxSpeed')}</span><strong>${formatSpeedMps(stat.max_speed_mps)}</strong></div>
      <div class="segment-metric-row"><span>${t('segmentStatsKicks')}</span><strong>${stat.kick_count}</strong></div>
      <div class="segment-metric-row"><span>${t('segmentStatsFalls')}</span><strong>${stat.fall_count}</strong></div>
    </div>
  `).join('');
}

async function refreshSelectedSegmentStats() {
  const segment = getSelectedSegment();
  if (!segment || !sessionKey) {
    selectedSegmentStats = null;
    segmentStatsPending = false;
    updateSegmentSummary();
    return;
  }

  const reqSeq = ++segmentStatsSeq;
  segmentStatsPending = true;
  updateSegmentSummary();

  try {
    const stats = await api(
      `/api/segment_stats?session_key=${encodeURIComponent(sessionKey)}&t0=${segment.t0.toFixed(3)}&t1=${segment.t1.toFixed(3)}&${possessionParams()}`,
    );
    if (reqSeq !== segmentStatsSeq) return;
    selectedSegmentStats = stats;
  } catch (e) {
    if (reqSeq !== segmentStatsSeq) return;
    selectedSegmentStats = null;
    console.warn('segment_stats failed:', e);
  } finally {
    if (reqSeq !== segmentStatsSeq) return;
    segmentStatsPending = false;
    updateSegmentSummary();
  }
}

// ── Load session ──────────────────────────────────────────────────────────────
elLoad.addEventListener('click', async () => {
  const selectedFiles = [..._selectedFiles];
  if (!selectedFiles.length) { alert(t('fileBrowserNoneSelected')); return; }
  elLoad.disabled = true;
  updateDownloadButton();
  elLoad.textContent = t('loading');
  elInfo.textContent = '';
  elLoadProgressWrap.style.display = 'flex';
  const setProgress = (_pct, label) => {
    elLoadProgressLabel.textContent = label;
  };
  setProgress(5, lang === 'ko' ? 'MCAP 파싱 중…' : 'Parsing MCAP…');
  sessionKey = null;
  gameSummary = null;
  summaryHalf = 'full';
  stopPlay();
  robotGaps = {};
  resetEventBookmarks();
  renderGameSummary();
  resetSegments();
  try {
    const data = await post('/api/load', {files: selectedFiles});
    setProgress(50, lang === 'ko' ? '히트맵 로드 중…' : 'Loading heatmap…');
    sessionKey = data.session_key;
    robotIds   = data.robot_ids;
    possPreload = null;
    resetSpaceControlPanel();
    gameSummary = data.summary ?? null;
    duration   = Number.isFinite(data.duration) ? data.duration : (gameSummary?.full_game?.duration ?? 0);
    summaryHalf = 'full';
    segmentPresets = normalizeSegments(data.segment_presets ?? data.segments ?? []);
    renderGameSummary();
    renderSegments();
    renderRobotGaps();

    // Load heatmap preload data (balls, kicks, robot positions for client-side rendering)
    hmPreload = null;
    if (hmLayer) hmLayer.clear();
    try {
      hmPreload = await api(`/api/heatmap_preload?session_key=${encodeURIComponent(data.session_key)}`);
      if (hmLayer) hmLayer.setData(hmPreload);
    } catch (e) { console.warn('heatmap_preload failed:', e); }
    setProgress(70, lang === 'ko' ? '공간 제어 분석 중…' : 'Analyzing space control…');
    try {
      scSamplesPreload = await api(`/api/space_control_samples?session_key=${encodeURIComponent(data.session_key)}`);
      buildSpaceControlTimeline();
      buildSpacingTimeline();
    } catch (e) {
      scSamplesPreload = null;
      scTimeline = [];
      spacingTimeline = null;
      console.warn('space_control_samples failed:', e);
    }
    setProgress(88, lang === 'ko' ? '점유 분석 중…' : 'Analyzing possession…');
    try {
      possPreload = await api(`/api/possession_preload?session_key=${encodeURIComponent(data.session_key)}&${possessionParams()}`);
      renderGameSummary();
    } catch (e) {
      possPreload = null;
      console.warn('possession_preload failed:', e);
    }

    robotGaps = {};
    for (const [rid, gaps] of Object.entries(data.robot_gaps ?? {})) {
      robotGaps[rid] = gaps;
    }
    renderRobotGaps();
    setEventBookmarks(data.event_bookmarks ?? []);
    renderTimelineMarkers();
    if (elTl) { elTl.max = duration; elTl.disabled = false; }
    if (elPlay) elPlay.disabled = false;
    setTime(0);
    fetchAndRender(0);

    // Robot filter buttons
    elFilter.innerHTML = '';
    visibleRobots.clear();
    visiblePerception.clear();
    visibleBasic.clear();
    visibleUdp.clear();
    for (const rid of robotIds) {
      visibleRobots.add(rid);
      visibleBasic.add(rid);
      const btn = document.createElement('button');
      btn.className = 'filter-btn active';
      btn.textContent = t('filterLabel', rid);
      btn.style.borderColor = court.robotColor(rid);
      btn.style.color = court.robotColor(rid);
      btn.dataset.rid = rid;
      btn.dataset.tipKo = `로봇 ${rid} 표시/숨김`;
      btn.dataset.tipEn = `Toggle robot ${rid} visibility`;
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.rid);
        if (visibleRobots.has(id)) { visibleRobots.delete(id); btn.classList.remove('active'); }
        else { visibleRobots.add(id); btn.classList.add('active'); }
        court.setVisibleRobots([...visibleRobots]);
      });
      elFilter.appendChild(btn);
    }
    court.setVisibleRobots([...visibleRobots]);
    court.setVisibleBasic([...visibleBasic]);
    court.setVisibleUdp([...visibleUdp]);

    // Heatmap select
    elHmRobot.innerHTML = `<option value="all">${t('allRobots')}</option>`;
    for (const rid of robotIds) {
      const opt = document.createElement('option');
      opt.value = rid;
      opt.textContent = t('robotOption', rid);
      elHmRobot.appendChild(opt);
    }

    // Build robot card skeletons ONCE (checkboxes live here permanently)
    setupRobotCards(robotIds);

    // Team picker
    _sessionTeamNumbers = data.team_numbers || [];
    if ((data.our_team_number ?? 0) !== 0) _ourTeamNumber = data.our_team_number;
    renderTeamPicker();

    const gcEvents = data.game_state_events ?? [];
    if (gcEvents.length) updateOverlay(gcEvents[0]);
    else resetOverlay();

    setProgress(100, lang === 'ko' ? '완료' : 'Done');
    elInfo.textContent = t('loadDone', duration.toFixed(1), robotIds.join(', '));
    elFileBrowser.classList.remove('open');
    _updateToggleBtn();
    updateDownloadButton();
  } catch(e) {
    elLoadSpinner.style.borderTopColor = '#ef4444';
    setProgress(0, lang === 'ko' ? '오류 발생' : 'Error');
    elInfo.textContent = t('loadErr', e.message);
    console.error(e);
  } finally {
    elLoadProgressWrap.style.display = 'none';
    elLoadSpinner.style.borderTopColor = '';
    elLoad.disabled = false;
    elLoad.textContent = t('btnLoad');
    updateDownloadButton();
  }
});

function filenameFromDisposition(headerValue, fallback) {
  if (!headerValue) return fallback;
  const utf8Match = headerValue.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) return decodeURIComponent(utf8Match[1]);
  const asciiMatch = headerValue.match(/filename=\"?([^\";]+)\"?/i);
  return asciiMatch ? asciiMatch[1] : fallback;
}

elDownload.addEventListener('click', async () => {
  if (!sessionKey || downloadBusy) return;

  const prevInfo = elInfo.textContent;
  downloadBusy = true;
  updateDownloadButton();
  elInfo.textContent = t('downloadPreparing');

  try {
    const response = await fetch(`/api/download_merged?session_key=${encodeURIComponent(sessionKey)}`);
    if (!response.ok) {
      let message = response.statusText;
      try {
        const data = await response.json();
        message = data.detail || message;
      } catch (_err) {}
      throw new Error(message);
    }

    const blob = await response.blob();
    const filename = filenameFromDisposition(
      response.headers.get('content-disposition'),
      'merged_session.zip',
    );
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
    elInfo.textContent = t('downloadDone', filename);
  } catch (e) {
    elInfo.textContent = t('downloadErr', e.message);
    console.error(e);
  } finally {
    downloadBusy = false;
    updateDownloadButton();
    if (elInfo.textContent === t('downloadPreparing')) elInfo.textContent = prevInfo;
  }
});

async function savePng() {
  const svgEl = $('court');
  const W = parseInt(svgEl.getAttribute('width'), 10);
  const H = parseInt(svgEl.getAttribute('height'), 10);
  if (!W || !H) return;

  // Clone and inject resolved CSS — class-based styles are lost on XMLSerializer
  const clone = svgEl.cloneNode(true);
  const styleEl = document.createElementNS('http://www.w3.org/2000/svg', 'style');
  styleEl.textContent = [
    '.field-bg   { fill: #166534; }',
    '.field-line { stroke: rgba(255,255,255,0.82); stroke-width: 1px; fill: none; }',
    '.goal       { stroke: rgba(255,255,255,0.82); stroke-width: 1.5px; fill: none; }',
    '.trail-line { fill: none; stroke-width: 1.5px; opacity: 0.45; }',
    '.heatmap-cell { opacity: 0.65; }',
  ].join('\n');
  clone.insertBefore(styleEl, clone.firstChild);

  const svgStr = new XMLSerializer().serializeToString(clone);
  const blob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
  const blobUrl = URL.createObjectURL(blob);

  try {
    const img = await new Promise((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = reject;
      i.src = blobUrl;
    });

    const canvas = document.createElement('canvas');
    canvas.width = W;
    canvas.height = H;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#1a1a2e';
    ctx.fillRect(0, 0, W, H);
    ctx.drawImage(img, 0, 0);

    await new Promise(resolve => canvas.toBlob(pngBlob => {
      const pngUrl = URL.createObjectURL(pngBlob);
      const a = document.createElement('a');
      a.href = pngUrl;
      a.download = `field_${currentT.toFixed(1)}s.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(pngUrl);
      resolve();
    }, 'image/png'));
  } finally {
    URL.revokeObjectURL(blobUrl);
  }
}

elSavePng.addEventListener('click', () => savePng().catch(e => console.error('PNG 저장 실패:', e)));

elSegmentAdd.addEventListener('click', () => {
  const draft = getDraftSegment();
  if (!sessionKey || !draft) return;
  customSegmentCounter += 1;
  const saved = {
    ...draft,
    id: `custom:${customSegmentCounter}:${draft.t0.toFixed(3)}`,
    draft: false,
    custom_index: customSegmentCounter,
  };
  customSegments.push(saved);
  clearSegmentDraft();
  selectSegment(saved.id);
});

function startSegmentRename(segmentId, labelEl) {
  const seg = customSegments.find(s => s.id === segmentId);
  if (!seg) return;

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'segment-rename-input';
  input.value = seg.label || '';
  input.placeholder = t('segmentSavedFmt', seg.custom_index);
  labelEl.replaceWith(input);
  input.focus();
  input.select();

  let committed = false;
  function commit() {
    if (committed) return;
    committed = true;
    const v = input.value.trim();
    seg.label = v || undefined;
    renderSegments();
    updateSegmentSummary();
  }
  input.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); commit(); }
    if (e.key === 'Escape') { committed = true; renderSegments(); }
  });
  input.addEventListener('blur', commit);
}

elSegmentClear.addEventListener('click', () => {
  clearSelectedSegment({ clearDraft: true });
});

// ── Game overlay ──────────────────────────────────────────────────────────────
function resetOverlay() {
  elGoScore.textContent = '- : -';
  elGoState.textContent = '—';
  elGoState.className = 'go-chip';
  elGoSetplay.style.display = 'none';
  elGoTime.textContent = '—';
  if (elGoPossession) elGoPossession.hidden = true;
  elGoTeamA.textContent = '—';
  elGoTeamB.textContent = '—';
}

function updateOverlay(gc) {
  if (!gc) return;
  const teams = gc.teams || [];
  const ourTeam = teams.find(tm => isOurTeamNumber(tm.team_number));
  const oppTeam = teams.find(tm => !isOurTeamNumber(tm.team_number) && tm.team_number > 0);
  if (ourTeam && oppTeam) {
    elGoTeamA.textContent = `Team ${oppTeam.team_number}`;
    elGoTeamB.textContent = `Team ${ourTeam.team_number}`;
    elGoScore.textContent = `${oppTeam.score} : ${ourTeam.score}`;
  } else if (teams.length >= 2) {
    elGoTeamA.textContent = `Team ${teams[0].team_number}`;
    elGoTeamB.textContent = `Team ${teams[1].team_number}`;
    elGoScore.textContent = `${teams[0].score} : ${teams[1].score}`;
  }
  elGoState.textContent = stateName(gc.state);
  elGoState.className = 'go-chip ' + (
    gc.state === 3 ? 'playing' : gc.state === 1 ? 'ready' :
    gc.state === 2 ? 'set'     : gc.state === 4 ? 'finished' :
    gc.stopped     ? 'stopped' : ''
  );
  const sp = setplayName(gc.set_play);
  if (sp) { elGoSetplay.textContent = sp; elGoSetplay.style.display = ''; }
  else { elGoSetplay.style.display = 'none'; }
  const secs = gc.secs_remaining;
  const abs = Math.abs(secs);
  const sign = secs >= 0 ? '' : '+';
  const mm = String(Math.floor(abs / 60)).padStart(2, '0');
  const ss = String(abs % 60).padStart(2, '0');
  elGoTime.textContent = `${gc.first_half ? t('firstHalf') : t('secondHalf')}  ${sign}${mm}:${ss}`;
}

function updateLivePossession(frame) {
  if (!elGoPossession) return;
  const ball = frame.ball;
  if (!ball || ball.age > 1.0) {
    elGoPossession.hidden = true;
    return;
  }
  let minOur = Infinity, minEnemy = Infinity;
  for (const r of (frame.robots || [])) {
    if (r.x == null) continue;
    const d = Math.hypot(r.x - ball.x, r.y - ball.y);
    if (d < minOur) minOur = d;
  }
  for (const e of (frame.enemies || [])) {
    const d = Math.hypot(e.x - ball.x, e.y - ball.y);
    if (d < minEnemy) minEnemy = d;
  }
  const ourNear   = minOur   < possessionDistM;
  const enemyNear = minEnemy < possessionDistM;
  let state, cls;
  if (ourNear && enemyNear) {
    state = t('possessionLiveStuck');  cls = 'poss-stuck';
  } else if (ourNear) {
    state = t('possessionLiveOur');    cls = 'poss-our';
  } else if (enemyNear) {
    state = t('possessionLiveEnemy');  cls = 'poss-enemy';
  } else {
    state = t('possessionLiveLoose');  cls = 'poss-loose';
  }
  elGoPossession.textContent = state;
  elGoPossession.className = `go-possession-chip ${cls}`;
  elGoPossession.hidden = false;
}

// ── Robot cards ───────────────────────────────────────────────────────────────
// setupRobotCards: called ONCE on session load.
// Creates card skeleton + vision checkbox. Never recreated during playback.
function setupRobotCards(ids) {
  elCards.innerHTML = '';
  visiblePerception.clear();

  for (const rid of ids) {
    const color = court.robotColor(rid);
    const card = document.createElement('div');
    card.className = 'robot-card';
    card.id = `rc-${rid}`;

    // Static title
    const title = document.createElement('div');
    title.className = 'card-title';
    const dotSpan = document.createElement('span');
    dotSpan.className = 'card-dot';
    dotSpan.style.background = color;
    const labelSpan = document.createElement('span');
    labelSpan.setAttribute('data-robot-label', rid);
    labelSpan.textContent = t('robotLabel', rid);
    title.appendChild(dotSpan);
    title.appendChild(labelSpan);
    const liftedBadge = document.createElement('span');
    liftedBadge.className = 'lifted-badge';
    liftedBadge.id = `rc-lifted-${rid}`;
    liftedBadge.setAttribute('data-i18n', 'fallen');
    liftedBadge.textContent = t('fallen');
    liftedBadge.style.display = 'none';
    title.appendChild(liftedBadge);
    card.appendChild(title);

    // Dynamic rows (updated each frame via updateRobotCards)
    const posRow = document.createElement('div');
    posRow.className = 'card-row';
    posRow.id = `rc-pos-${rid}`;
    card.appendChild(posRow);

    const angleRow = document.createElement('div');
    angleRow.className = 'card-row';
    angleRow.id = `rc-angle-${rid}`;
    card.appendChild(angleRow);

    const btRow = document.createElement('div');
    btRow.className = 'card-row';
    btRow.id = `rc-bt-${rid}`;
    btRow.style.display = 'none';
    card.appendChild(btRow);

    // Per-robot toggles (basic / vision / UDP) — created once, never recreated
    const divider = document.createElement('div');
    divider.className = 'card-vision-row';

    // Basic-position toggle
    const basicLabel = document.createElement('label');
    basicLabel.className = 'vision-label';
    basicLabel.dataset.tipKo = 'localization 기반 기본 위치 표시/숨김';
    basicLabel.dataset.tipEn = 'Toggle localization-based robot position';
    const basicCb = document.createElement('input');
    basicCb.type = 'checkbox';
    basicCb.className = 'vision-cb';
    basicCb.checked = true;
    basicCb.addEventListener('change', () => {
      if (basicCb.checked) { visibleBasic.add(rid); basicLabel.style.color = color; }
      else                 { visibleBasic.delete(rid); basicLabel.style.color = ''; }
      court.setVisibleBasic([...visibleBasic]);
    });
    const basicDot = document.createElement('span');
    basicDot.className = 'vision-dot';
    basicDot.style.background = color;
    const basicText = document.createElement('span');
    basicText.setAttribute('data-i18n', 'basicLabel');
    basicText.textContent = t('basicLabel');
    basicLabel.appendChild(basicCb);
    basicLabel.appendChild(basicDot);
    basicLabel.appendChild(document.createTextNode(' '));
    basicLabel.appendChild(basicText);
    basicLabel.style.color = color;
    divider.appendChild(basicLabel);

    // Vision overlay toggle
    const label = document.createElement('label');
    label.className = 'vision-label';
    label.dataset.tipKo = '비전 인식 객체 오버레이 표시/숨김';
    label.dataset.tipEn = 'Toggle vision perception overlay';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'vision-cb';
    cb.addEventListener('change', () => {
      if (cb.checked) { visiblePerception.add(rid); label.style.color = color; }
      else            { visiblePerception.delete(rid); label.style.color = ''; }
      court.setVisiblePerception([...visiblePerception]);
    });
    const dot = document.createElement('span');
    dot.className = 'vision-dot';
    dot.style.background = color;
    const visionText = document.createElement('span');
    visionText.setAttribute('data-i18n', 'visionLabel');
    visionText.textContent = t('visionLabel');
    label.appendChild(cb);
    label.appendChild(dot);
    label.appendChild(document.createTextNode(' '));
    label.appendChild(visionText);
    divider.appendChild(label);

    // UDP overlay toggle
    const udpLabel = document.createElement('label');
    udpLabel.className = 'vision-label';
    udpLabel.dataset.tipKo = 'UDP 수신 위치 오버레이 표시/숨김';
    udpLabel.dataset.tipEn = 'Toggle UDP position overlay';
    const udpCb = document.createElement('input');
    udpCb.type = 'checkbox';
    udpCb.className = 'vision-cb';
    udpCb.addEventListener('change', () => {
      if (udpCb.checked) { visibleUdp.add(rid); udpLabel.style.color = color; }
      else               { visibleUdp.delete(rid); udpLabel.style.color = ''; }
      court.setVisibleUdp([...visibleUdp]);
    });
    const udpDot = document.createElement('span');
    udpDot.className = 'vision-dot';
    udpDot.style.background = color;
    const udpText = document.createElement('span');
    udpText.setAttribute('data-i18n', 'udpLabel');
    udpText.textContent = t('udpLabel');
    udpLabel.appendChild(udpCb);
    udpLabel.appendChild(udpDot);
    udpLabel.appendChild(document.createTextNode(' '));
    udpLabel.appendChild(udpText);
    divider.appendChild(udpLabel);

    card.appendChild(divider);

    elCards.appendChild(card);
  }
}

// updateRobotCards: called every frame. Updates only text/class, never touches checkboxes.
function updateRobotCards(robots) {
  for (const r of robots) {
    const card = document.getElementById(`rc-${r.id}`);
    if (!card) continue;

    card.className = 'robot-card' + (r.lifted ? ' lifted' : '');

    const liftedBadge = document.getElementById(`rc-lifted-${r.id}`);
    if (liftedBadge) liftedBadge.style.display = r.lifted ? '' : 'none';

    const posRow = document.getElementById(`rc-pos-${r.id}`);
    if (posRow) {
      const isUdp = r.pose_source === 'udp';
      const srcLabel = isUdp ? t('poseSourceUdp') : t('poseSourceLoc');
      const srcClass = isUdp ? 'src-udp' : 'src-loc';
      posRow.innerHTML =
        `${t('pos')}: <span>(${r.x.toFixed(2)}, ${r.y.toFixed(2)})</span><span class="src-badge ${srcClass}">${srcLabel}</span>`;
    }

    const angleRow = document.getElementById(`rc-angle-${r.id}`);
    if (angleRow) angleRow.innerHTML =
      `${t('angle')}: <span>${(r.theta * 180 / Math.PI).toFixed(1)}°</span>`;

    const btRow = document.getElementById(`rc-bt-${r.id}`);
    if (btRow) {
      if (r.bt_node) {
        btRow.style.display = '';
        btRow.innerHTML = `${t('btNode')}: <span>${prettifyBtNode(r.bt_node)}</span>`;
      } else {
        btRow.style.display = 'none';
      }
    }
  }
}

// ── Enemy cards ───────────────────────────────────────────────────────────────
function updateEnemyCards(enemies) {
  if (!enemies.length) {
    elEnemy.innerHTML = `<p class="muted" style="font-size:10px">${t('noEnemies')}</p>`;
    return;
  }
  elEnemy.innerHTML = '';
  enemies.forEach((e, i) => {
    const card = document.createElement('div');
    card.className = 'enemy-card';
    card.innerHTML = `
      <div class="card-row" style="font-weight:600;color:#fca5a5;margin-bottom:2px">E${i+1}<span class="src-badge src-coop">${t('enemySource')}</span></div>
      <div class="card-row">${t('pos')}: <span>(${e.x.toFixed(2)}, ${e.y.toFixed(2)})</span></div>
    `;
    elEnemy.appendChild(card);
  });
}

// ── Ball card ─────────────────────────────────────────────────────────────────
function updateBallCard(ball) {
  if (!ball) {
    elBallCard.innerHTML = `<p class="muted" style="font-size:10px">${t('ballNoData')}</p>`;
    return;
  }
  elBallCard.innerHTML = `
    <div class="ball-card">
      <div class="card-row">${t('pos')}: <span>(${ball.x.toFixed(2)}, ${ball.y.toFixed(2)})</span><span class="src-badge src-det">detection</span></div>
      <div class="card-row">${t('labelTime')}: <span>${t('ballAge', ball.age)}</span></div>
    </div>
  `;
}

// ── Heatmap helpers ───────────────────────────────────────────────────────────
function _hmPids() {
  const mode = elHmMode.value;
  // ball mode: no per-robot distinction (merged data)
  if (mode === 'ball') return new Set();
  // robot / kick mode: respect robot select filter
  const val = elHmRobot.value;
  return val === 'all' ? new Set(robotIds) : new Set([parseInt(val)]);
}

function _hmTimeRange() {
  const hs = hmPreload?.half_split ?? null;
  const timeMode = elHmTime.value;
  if (timeMode === 'segment') {
    return getSelectedSegmentRange() || [0, duration];
  }
  if (timeMode === 'first')  return [0, hs ?? duration];
  if (timeMode === 'second') return [hs ?? 0, duration];
  return [0, duration];
}

function _robotSelectVisible(mode) {
  // Show robot filter for modes that have per-robot data
  elHmRobot.style.display = mode !== 'ball' ? '' : 'none';
}

function refreshHeatmap() {
  if (!hmLayer || !hmPreload) return;
  if (!heatmapEnabled) { hmLayer.clear(); return; }
  const mode = elHmMode.value;
  const pids = _hmPids();
  _robotSelectVisible(mode);
  const [minT, maxT] = _hmTimeRange();
  hmLayer.render(mode, pids, minT, maxT);
}

// ── Toggles ───────────────────────────────────────────────────────────────────
elHm.addEventListener('change', () => {
  heatmapEnabled = elHm.checked;
  refreshHeatmap();
});
elHmMode.addEventListener('change', () => {
  _robotSelectVisible(elHmMode.value);
  if (heatmapEnabled) refreshHeatmap();
});
elHmRobot.addEventListener('change', () => { if (heatmapEnabled) refreshHeatmap(); });
elHmTime.addEventListener('change',  () => { if (heatmapEnabled) refreshHeatmap(); });

elTrail.addEventListener('change', () => {
  trailEnabled = elTrail.checked;
  court.setShowTrail(trailEnabled);
  if (!trailEnabled) court.clearTrail();
});
elDest.addEventListener('change',    () => court.setShowDest(elDest.checked));
elBall.addEventListener('change',    () => court.setShowBall(elBall.checked));
elEnemies.addEventListener('change', () => court.setShowEnemies(elEnemies.checked));
elVoronoi.addEventListener('change', () => court.setShowVoronoi(elVoronoi.checked));
elVoronoiColorMode.addEventListener('change', () => {
  court.setVoronoiColorMode(elVoronoiColorMode.value);
});
elFormationToggle?.addEventListener('change', () => {
  if (!elFormationToggle.checked) {
    if (_popupSvgEl === elFormationChart) closeChartPopup();
    court.clearFormationOverlay();
    if (elFormationSection) elFormationSection.hidden = true;
  } else {
    renderFormationChart();
  }
});

// ── Playback: setTime / fetchAndRender ────────────────────────────────────────
function setTime(t_) {
  currentT = Math.max(0, Math.min(t_, duration));
  if (elTl) elTl.value = currentT;
  if (elTime) elTime.textContent = `${currentT.toFixed(1)}s / ${duration.toFixed(1)}s`;
  updateEventBookmarkActiveState();
  updatePossessionTimelineMarker(currentT);
  updateFormationChartMarker(currentT);
  if (heatmapEnabled && hmLayer && hmPreload && elHmTime?.value === 'progressive') {
    hmLayer.renderProgressive(elHmMode.value, _hmPids(), currentT);
  }
}

let _pending = false, _queued = null;
async function fetchAndRender(t_) {
  if (!sessionKey) return;
  if (_pending) { _queued = t_; return; }
  _pending = true;
  try {
    const frame = await api(`/api/frame?session_key=${encodeURIComponent(sessionKey)}&t=${t_.toFixed(3)}`);
    court.updateFrame(frame);
    updateSpaceControlPanel(frame);
    updateRobotCards(frame.robots || []);
    updateEnemyCards(frame.enemies || []);
    updateBallCard(frame.ball ?? null);
    if (frame.game_state) updateOverlay(frame.game_state);
    updateLivePossession(frame);
    renderSpaceControlChart();
    if (elFormationToggle?.checked) {
      const formation = computeFormation(frame.robots || []);
      court.drawFormationOverlay(frame.robots || []);
      renderFormationPanel(formation);
    }
    if (trailEnabled) {
      const trail = await api(`/api/trail?session_key=${encodeURIComponent(sessionKey)}&t=${t_.toFixed(3)}&window=20`);
      court.setTrail(trail.robots || {});
    }
  } catch(e) { console.warn('fetch error', e); }
  _pending = false;
  if (_queued !== null) { const next = _queued; _queued = null; fetchAndRender(next); }
}

function seekBy(deltaSec) {
  setTime(currentT + deltaSec);
  fetchAndRender(currentT);
}

function togglePlay() { playing ? stopPlay() : startPlay(); }

function startPlay() {
  if (duration <= 0 || !sessionKey) return;
  playing = true;
  if (elPlay) elPlay.textContent = '⏸';
  lastWall = performance.now();
  playRaf = requestAnimationFrame(playStep);
}

function stopPlay() {
  playing = false;
  if (elPlay) elPlay.textContent = '▶';
  if (playRaf) { cancelAnimationFrame(playRaf); playRaf = null; }
}

async function playStep(now) {
  if (!playing) return;
  const dt = (now - lastWall) / 1000 * speed;
  lastWall = now;
  const seg = loopSelectedSegment ? getSelectedSegment() : null;
  if (seg) {
    let next = currentT + dt;
    if (next >= seg.t1) next = seg.t0;
    setTime(next);
  } else {
    setTime(currentT + dt);
    if (currentT >= duration) { stopPlay(); return; }
  }
  await fetchAndRender(currentT);
  if (playing) playRaf = requestAnimationFrame(playStep);
}

// ── Event bookmarks ────────────────────────────────────────────────────────────
function setEventBookmarks(bms) {
  eventBookmarks = normalizeEventBookmarks(bms);
  renderEventFilterButtons();
  renderEventBookmarks();
  renderTimelineMarkers();
}

function resetEventBookmarks() {
  eventBookmarks = [];
  if (elTlMarkers) elTlMarkers.innerHTML = '';
  hideTimelineTooltip();
  renderEventFilterButtons();
  renderEventBookmarks();
}

function renderEventFilterButtons() {
  if (!elBookmarkFilter) return;
  elBookmarkFilter.innerHTML = '';
  const availableKinds = new Set(eventBookmarks.map(e => e.kind));
  for (const kind of EVENT_KINDS) {
    const active = visibleEventKinds.has(kind);
    const available = availableKinds.has(kind);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `marker-filter-btn ${eventKindClass(kind)}${active ? ' active' : ''}`;
    btn.textContent = formatEventTypeLabel(kind, { short: true });
    btn.style.setProperty('--marker-color', eventKindAccent(kind));
    btn.disabled = !available;
    btn.setAttribute('aria-pressed', String(active));
    btn.addEventListener('click', () => {
      if (visibleEventKinds.has(kind)) visibleEventKinds.delete(kind);
      else visibleEventKinds.add(kind);
      renderEventFilterButtons();
      renderEventBookmarks();
      renderTimelineMarkers();
    });
    elBookmarkFilter.appendChild(btn);
  }
}

function renderEventBookmarks() {
  if (!elBookmarkList) return;
  elBookmarkList.innerHTML = '';
  const visible = eventBookmarks.filter(e => visibleEventKinds.has(e.kind));
  if (!visible.length) {
    const msg = document.createElement('span');
    msg.className = 'muted';
    msg.style.fontSize = '10px';
    msg.textContent = eventBookmarks.length ? t('eventBookmarksFilteredEmpty') : t('eventBookmarksNone');
    elBookmarkList.appendChild(msg);
    return;
  }
  for (const event of visible) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = `bookmark-chip ${eventKindClass(event.kind)}`;
    chip.dataset.eventIndex = event._index;
    chip.style.borderColor = eventAccentColor(event);
    const timeSpan = document.createElement('span');
    timeSpan.className = 'bookmark-time';
    timeSpan.textContent = formatEventTime(event.t);
    const labelSpan = document.createElement('span');
    labelSpan.className = 'bookmark-text';
    labelSpan.textContent = formatEventLabel(event, { short: true });
    chip.appendChild(timeSpan);
    chip.appendChild(labelSpan);
    chip.addEventListener('click', () => jumpToBookmark(event, chip));
    elBookmarkList.appendChild(chip);
  }
  updateEventBookmarkActiveState();
}

function updateEventBookmarkActiveState() {
  let activeIndex = -1;
  let bestDist = Infinity;
  const threshold = 0.18;
  getVisibleEventBookmarks().forEach((event) => {
    const dist = Math.abs(event.t - currentT);
    if (dist <= threshold && dist < bestDist) {
      activeIndex = event._index;
      bestDist = dist;
    }
  });

  document.querySelectorAll('.timeline-marker, .bookmark-chip').forEach(el => {
    const idx = Number(el.dataset.eventIndex);
    el.classList.toggle('active', idx === activeIndex);
  });
}

function jumpToBookmark(event, sourceEl = null) {
  if (!sessionKey || !Number.isFinite(event?.t)) return;
  hideTimelineTooltip();
  stopPlay();
  setTime(event.t);
  fetchAndRender(currentT);
  if (sourceEl) {
    sourceEl.scrollIntoView({ block: 'nearest', inline: 'center' });
  }
}

function renderTimelineMarkers() {
  if (!elTlMarkers || duration <= 0) return;
  elTlMarkers.innerHTML = '';
  const visible = eventBookmarks.filter(e => visibleEventKinds.has(e.kind));
  for (const event of visible) {
    const pct = Math.max(0, Math.min(100, (event.t / duration) * 100));
    const marker = document.createElement('button');
    marker.type = 'button';
    marker.className = `timeline-marker ${eventKindClass(event.kind)}`;
    marker.dataset.eventIndex = String(event._index);
    marker.style.left = `${pct}%`;
    marker.style.color = eventAccentColor(event);
    marker.addEventListener('click', () => jumpToBookmark(event));
    marker.addEventListener('mouseenter', () => showTimelineInfoTooltip(
      marker,
      formatEventTypeLabel(event),
      formatEventTime(event.t),
      formatEventDetail(event),
    ));
    marker.addEventListener('mouseleave', hideTimelineTooltip);
    marker.addEventListener('focus', () => showTimelineInfoTooltip(
      marker,
      formatEventTypeLabel(event),
      formatEventTime(event.t),
      formatEventDetail(event),
    ));
    marker.addEventListener('blur', hideTimelineTooltip);
    elTlMarkers.appendChild(marker);
  }
  updateEventBookmarkActiveState();
}

// ── Playback controls event listeners ─────────────────────────────────────────
elTl?.addEventListener('input', () => { setTime(parseFloat(elTl.value)); fetchAndRender(currentT); });
elPlay?.addEventListener('click', () => togglePlay());
elSpeed?.addEventListener('change', () => { speed = parseFloat(elSpeed.value) || 1; });
elSeekStep?.addEventListener('change', () => { seekStepSec = parseFloat(elSeekStep.value) || 1; });

elSegmentSetA?.addEventListener('click', () => {
  if (!sessionKey) return;
  segmentDraftA = currentT;
  normalizeDraftPoints();
  if (getDraftSegment()) selectSegment('draft');
  else {
    renderSegments();
    updateSegmentSummary();
  }
});
elSegmentSetB?.addEventListener('click', () => {
  if (!sessionKey) return;
  segmentDraftB = currentT;
  normalizeDraftPoints();
  if (getDraftSegment()) selectSegment('draft');
  else {
    renderSegments();
    updateSegmentSummary();
  }
});
elSegmentLoop?.addEventListener('change', () => {
  loopSelectedSegment = !!elSegmentLoop.checked;
  updateSegmentButtons();
});

document.addEventListener('keydown', e => {
  if (isInteractiveElement(document.activeElement)) return;
  if (e.key === ' ')           { e.preventDefault(); togglePlay(); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); seekBy(seekStepSec); }
  else if (e.key === 'ArrowLeft')  { e.preventDefault(); seekBy(-seekStepSec); }
});

// ── Init ──────────────────────────────────────────────────────────────────────
applyLang();
api('/api/field_config').then(cfg => {
  court.init(cfg);
  court.setVoronoiColorMode(elVoronoiColorMode.value);
  hmLayer = new HeatmapLayer(court, rid => court.robotColor(rid));
  court.onResize(() => {
    if (!heatmapEnabled || !hmLayer) return;
    refreshHeatmap();
  });
}).catch(console.error);

api('/api/team_config').then(cfg => {
  _ourTeamNumber = cfg.our_team_number ?? 0;
  _sessionTeamNumbers = cfg.team_numbers ?? [];
  renderTeamPicker();
}).catch(() => {});

const elTeamPickerSel = document.getElementById('team-picker-select');
if (elTeamPickerSel) {
  elTeamPickerSel.addEventListener('change', async () => {
    const num = parseInt(elTeamPickerSel.value) || 0;
    _ourTeamNumber = num;
    await fetch('/api/team_config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ our_team_number: num }),
    }).catch(() => {});
  });
}

resetSpaceControlPanel();
updateBallCard(null);
refreshSessions();
updateDownloadButton();
