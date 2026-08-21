# TODO — W-first 데이터 마트 재설계 및 안전 복구

최종 갱신: **2026-08-21 KST**

상태: **P3 완료, P4 구현 시작 전**

다음 세션 시작점: **P4 — heart-rate 비용 제거와 wearable detail**

이 문서는 다음 세션이 바로 작업을 이어가기 위한 **실행 계약서**다. 과거
작업일지나 완료 이력은 반복하지 않는다.

- 아키텍처와 개발 규칙: `AGENTS.md`
- 결정의 배경: `INVITES_LOOP_BI_DECISION_LOG.md`
- 측정이 기존 결정을 뒤집은 기록: `IMPLEMENTATION_PLAN.md`
- 운영 인수인계: `HANDOVER.md`
- PII 분류와 보존 범위: `PII_INVENTORY.md`
- 로컬 전략 원본(버전 관리 밖, 참고용): `docs/business_intelligence/`

판단이 충돌하면 아래 순서를 따른다.

1. 현재 source/staging에서 측정한 사실
2. grain·reconciliation·freshness·PII 테스트
3. 이 문서에 명시한 gate와 완료 조건
4. 전략 문서와 과거 설계 문서

전략 문서는 의도와 가설을 제공하지만 물리 모델의 절대 규칙은 아니다.

---

## 0. 다음 세션이 시작할 때 반드시 지킬 것

### 0.1 금지

P0~P5가 끝나기 전에는 아래 작업을 하지 않는다.

- **bare full build 금지:** `uv run dbt build --project-dir dbt`
- `transform_dbt_build` DAG 활성화 또는 scheduler 시작 금지
- Superset의 전체 marts dataset 자동 재등록 금지
- 추가 `TRUNCATE`, landing 삭제, watermark 수동 삭제 금지
- storage 여유를 확인하지 않은 대형 쿼리·상세 wearable build 금지
- 현재 site를 과거 event의 발생 당시 site로 사용하는 분석 금지

`dbt/profiles.yml`의 기본 threads는 4다. 현재 transform DAG도 threads를
지정하지 않고 전체 graph를 실행하며, freshness 실패를 `|| true`로 무시하고,
실패 시 전체 build를 한 번 자동 재시도한다. 이 상태로 실행하면 안 된다.

### 0.2 기존 작업 보존

2026-08-21 현재 `main`의 기준 commit은 `35b0ed4`이며 아래 변경은 아직
commit되지 않았다. 모두 현재 작업의 일부이므로 덮어쓰거나 되돌리지 않는다.
다음 세션은 반드시 `git status --short`와 각 diff부터 읽는다.

| 파일 | 현재 의도 |
|---|---|
| `.gitignore` | `todo.md`를 tracking 대상으로 전환 |
| `dags/elt_to_staging.py` | iccoli target 수 34 → 37 |
| `src/invites_loop_bi/config/iccoli_targets.py` | search/share 3개 target 추가 |
| `tests/extract/test_config_targets.py` | 신규 cohort filter·PII test 추가 |
| `todo.md` | 이 실행계획 |

별도 요청이 없으면 commit, push, 배포하지 않는다.

### 0.3 처음 실행해도 안전한 명령

아래는 파일·graph 확인용이며 database relation을 만들지 않는다.

```bash
git status --short
git diff -- src/invites_loop_bi/config/iccoli_targets.py
git diff -- tests/extract/test_config_targets.py
INVITES_LOOP_BI_TEST_OFFLINE=1 uv run pytest
source setup_env.sh
uv run dbt parse --project-dir dbt
uv run dbt compile --project-dir dbt
```

selector를 만든 뒤에는 mutation 전에 반드시 선택 graph를 확인한다.

```bash
uv run dbt ls --project-dir dbt --selector daily_core
uv run dbt ls --project-dir dbt --selector wearable_detail
```

P0~P5 중에도 신규 소형 모델의 **targeted build**는 가능하다. 단, 먼저
`dbt ls --select ...`로 선택 graph를 확인하고, heart-rate/wearable detail
경로가 포함되지 않은 명시적 model selection만 `--threads 1 --fail-fast`로
실행한다. P6는 최초의 완전한 `daily_core` build다.

---

## 1. 이번 재설계의 목적과 경계

### 1.1 목적

작고 안전하게 매일 갱신할 수 있는 **Wellness-first core mart**를 만든다.

```text
W-A 획득·활성
  → W-B 참여·잔존
    → W-C 행동수행
      → W-D 위험점수 이동
```

현재 관측 가능한 Wellness 지표는 `ACTIVE`로, admission·LOS·readmission·
claim·RCM 등 데이터가 없는 Medical/Financial 지표는 `ROADMAP`으로
분리한다.

일반 BI 경로는 atomic event, 일별 wearable 집계, dense user-day/month panel을
사용한다. 대형 source-grain wearable observation은 상세 분석 경로로 분리한다.

### 1.2 이번 작업의 비목표

- 데이터가 없는 ED, 입원, LOS, 재입원, claim, billing fact를 미리 만들지 않는다.
- IRS 변화나 앱 행동을 임상 효과 또는 인과 효과라고 부르지 않는다.
- D0~D7 등을 조합한 거대한 사전 계산 `cohort_id`를 만들지 않는다.
- user, site, milestone, score, 누적 행동을 한 accumulating snapshot에 합치지 않는다.
- 일 1회 batch를 실시간 임상 모니터링으로 부르지 않는다.
- USCDI/FHIR mapping으로 mart grain이나 KPI 타당성을 정당화하지 않는다.
- historical site attribution은 upstream 변경 이력이 확보되기 전까지 만들지 않는다.
- Superset production hosting과 endpoint 이전을 mart 재설계의 선행조건으로
  만들지 않는다.

---

## 2. 2026-08-21 기준 확인된 사실

이 절의 운영 데이터 행 수치는 **2026-08-21 extraction 기준선**이다. source,
landing, mart 행 수는 테스트 상수로 hard-code하지 않고 현재 데이터와 동적으로
reconciliation한다. 단, 선언된 target 총수 128과 37/16/36/5/34 분할은 P0에서
검증할 config 계약이므로 명시적으로 고정한다.

### 2.1 Pipeline과 database

- 설정된 extraction target은 총 **128개**다.
  - iccoli 37
  - ichms 16
  - sibc 36
  - irs 5
  - discovery 34
- `stg_meta.watermarks`의 128개 행은 현재 모두 `SUCCESS`다.
- source 기준 2026-08-21 08:00 KST까지 EL을 수행했고 신규 iccoli 테이블의
  최신 `_loaded_at`은 약 08:58 KST다.
- 2026-08-20 사고 대응 `TRUNCATE` 이후 비어 있던 core 중 P3 targeted
  build가 dimension, atomic fact, lifecycle, 81,745행 user-day와 2,996행
  user-month를 복구했다. 이것은 전체 `daily_core` recovery build나 P5
  semantic acceptance가 아니다. 여섯 raw wearable fact는 여전히
  `marts_detail`에서 0행이며 Superset refresh/대표 chart 검증은 실행하지
  않았다.
- 마지막 과거 정상 기록인 `dbt build 388/388`과 `pytest 125/125`는 현재
  완료 기준이 아니다.
- 현재 offline test 기준선은 **95 passed, 32 skipped**다. live suite는
  재실행하지 않았다.
- EL과 dbt는 여전히 수동 실행이다. 선언된 Airflow schedule은 실제 운영
  이력이 없다.

### 2.2 Storage 사고 이후 조건

- 운영 DB와 `invites_dw`는 같은 PostgreSQL endpoint의 storage·I/O·CPU를
  공유한다.
- Azure storage는 128GB에서 256GB로 증설됐지만 이는 단기 여유일 뿐
  resource isolation이 아니다.
- 사고 당시 직접 촉발 요인은 약 901만 landing heart-rate 행의 반복
  `GROUP BY`와 약 888만 행 detail fact의 full rebuild가 threads=4로 겹친
  것이었다.
- 현재 `stg_discovery__lifelog_wearable_heartrate`는 view라 model/test마다
  같은 대형 집계를 다시 계산한다.
- `stg_discovery__lifelog_wearable_day`도 raw heart-rate를 별도로 읽는다.
- `fct_wearable_heartrate`를 소비하는 canonical `v_pi_*`는 없다.
- SQL의 DB size와 `temp_bytes`는 비교 지표일 뿐 Azure 전체 filesystem
  여유를 대신하지 않는다. 실제 stop line은 Azure Monitor storage를 쓴다.

초기 stop line:

| Azure storage 사용률 | 동작 |
|---|---|
| 70% 미만 | 계측하며 실행 가능 |
| 70% 이상 | 경고. 예상 peak와 운영 부하를 확인한 뒤 판단 |
| 80% 이상 | 신규 dbt build 시작 금지 |

### 2.3 신규 iccoli landing

| landing table | PK | rows | actor users | 관측 의미 |
|---|---|---:|---:|---|
| `stg_iccoli.tb_search_log` | `search_log_no` | 514 | 85 | 검색 event |
| `stg_iccoli.tb_share_info` | `share_no` | 1,141 | 151 | 공유 link/object 생성 |
| `stg_iccoli.tb_share_log` | `share_log_no` | 572 | 63 | 공유 후속 interaction 후보 |

- 세 신호의 actor 합집합은 176명이다.
- 기존 login/action에 전혀 없던 사용자는 1명뿐이다. 신규 데이터는
  acquisition 확대보다 engagement depth와 share funnel을 설명한다.
- 1,141개 share link 중 후속 log가 있는 `share_no`는 181개이며 그
  link들에서 572개 log가 발생했다.
- `share_info` row 수, interacted `share_no` 수, `share_log` row 수를
  동일한 “공유 수”로 부르지 않는다.
- `share_info → share_log`는 `share_no`만으로 현재 모두 연결되며 orphan,
  sender mismatch는 없다.
- 기존 `fct_app_action`에도 일부 share action이 있어 단순 합산하면 의미가
  중복될 수 있다.
- `share_log`는 발신자의 능동 행동이 아니라 수신 측 후속 결과일 수 있다.
  source 의미가 확정되기 전에는 발신자의 active-day로 세지 않는다.

### 2.4 현재 cohort와 site

- SiBC cohort: 437명
- current approved site:
  - Ulsan 393명
  - Jeju 44명
- 437명 모두 현재 approved site가 정확히 하나 있다.
- 이 관계는 current-state filter다. 알려진 in-place site flip에는 과거 값과
  실제 전환시각이 없으므로 historical/as-of attribution은 불가능하다.

---

## 3. 바꾸지 않을 모델링 규칙

1. 모든 fact는 SQL header에 grain을 선언하고 unique grain test를 가진다.
2. `fct_user_day`는 zero day를 포함한 dense panel을 유지한다.
3. upper bound는 `current_date`가 아니라 관측 frontier다.
4. enrolment 이전 실제 activity가 있으면 spine도 그 날짜까지 확장한다.
5. `assert_user_day_spine_loses_no_activity`를 삭제하지 않고 신규 channel까지
   확장한다.
6. 사용자 key는 mart에 `user_id`만 노출한다. source serial key는 staging에서
   변환한다.
7. direct identifier, free text, 접근 token과 불필요한 외부 사용자 key는
   최소한 일반 mart에 절대 노출하지 않는다.
8. source-shaped event를 하나의 omnibus snapshot에 합치지 않는다.
9. numerator와 denominator는 같은 metric relation에서 함께 검증 가능해야 한다.
10. source가 stale하거나 eligibility가 없는 날짜의 0을 “무활동”으로
    해석하지 않는다.
11. 현재 site는 current filter에만 사용하고 event-time fact에 과거 site로
    붙이지 않는다.
12. IRS/IRS+/LRS/MRS/PRS는 1~100 rank이며 서로 더하거나 residual을 만들지 않는다.
13. metric 정의는 한 view에 하나씩 두고 git에서 review한다.
14. detail wearable과 daily core를 같은 build 단위로 묶지 않는다.

---

## 4. 목표 물리 구조

```text
stg_* landing
  ↓
dbt staging
  - source별 cast/dedupe
  - user key translation
  - PII 차단
  ↓
재사용 physical intermediate
  - 대형 dedupe/집계를 한 번만 계산
  ↓
marts
  - conformed dimensions
  - atomic core facts
  - dense panels
  - thin metric views
  └─ superset_reader가 읽는 유일한 업무 schema

marts_detail
  - source-grain wearable observations
  └─ 분석가 전용, daily core와 Superset 일반 role에서 제외
```

### 4.1 Model 처리 방침

아래 이름은 구현 기준이다. `fct_share_interaction_event`처럼 source 의미가
확정되지 않은 이름은 중립적으로 유지하고 설명에 불확실성을 기록한다.

| model family | grain / 처리 |
|---|---|
| `dim_date`, `dim_disease`, `dim_action`, `dim_device_type`, `dim_deployment_site` | 유지 |
| `dim_user` | user 1행. 신원·가입·현재 profile만 남기도록 축소 |
| `dim_user.is_observable_*` | 제거. time-aware coverage/eligibility relation으로 이동 |
| current site | `bridge_user_site_current.current_site_id`로 분리, 역사 의미 없음 |
| `bridge_user_site_current` | 구현됨. user × current site, 역사 의미 없음 |
| `fct_user_milestone` | 구현됨. user × milestone, 실제 temporal precision 보존 |
| `fct_app_action` | 유지. 신규 event와 의미 중복을 taxonomy로 통제 |
| `fct_app_search_event` | 신규. grain = `search_log_no` |
| `fct_share_link` | 신규. grain = `share_no` |
| `fct_share_interaction_event` | 신규. grain = `share_log_no` |
| `fct_coaching_event` | 유지 |
| `fct_measurement` | 유지하되 device/source transaction을 포함한 grain 재검증 |
| `fct_user_disease_day` | 유지. IRS derived score라는 의미를 명시 |
| `fct_wearable_day` | core의 sparse 일별 intensity fact로 유지 |
| `fct_user_day` | canonical facts에서 조립하도록 재작성 |
| `fct_user_month` | 신규. user × calendar/relative month panel |
| `fct_user_day_wide` | 미래정보 플래그를 제거한 Superset serving relation |
| 여섯 `fct_wearable_*` | `marts_detail`로 이동, daily core에서 제외 |
| 기존 `v_pi_*` | W-A/B/C/D metric contract에 따라 keep/replace/retire |
| `v_bridge_pi_to_kpi` | source가 없는 Medical KPI의 gap register로 유지 |

### 4.2 Metric contract

기존 4-tuple `Entity × Time alignment × Aggregation × Denominator`를
최소 규칙으로 유지하고 아래를 추가한다.

`dbt/seeds/metric_registry.csv` 또는 동등한 git-tracked contract의 필수 항목:

- `metric_id`, `metric_version`, 의미 기반 이름
- `metric_tier`
- `evidence_status`: `OBSERVED | DERIVED | HYPOTHESIS | ROADMAP`
- `evidence_reference`, `population_scope`
- `entity`, `grain`
- `aggregation`, `numerator`, `denominator`, `eligibility`
- `time_alignment`, `censoring_rule`, `timezone`
- `source_frontier`, `data_as_of`
- `assumption_version`: model, hypothesis, simulation, forecast, valuation에
  해당할 때 필수
- `small_cell_rule`
- `metric_owner`, `decision_owner`

KPI 순번은 문서마다 바뀌므로 `kpi_1` 같은 번호를 model/ID에 새기지 않는다.
population, denominator, eligibility, grain, time alignment가 달라지면 동일 metric의
표현 변경이 아니라 새 version 또는 새 ID다. 외부 문헌은 hypothesis와 pilot 설계를
뒷받침할 수 있지만 로컬 관측 근거가 아니며, simulation·forecast·valuation은 입력이
관측값이어도 `OBSERVED`를 상속하지 않는다. 공통 schema나 FHIR/USCDI vocabulary도
공통 population 또는 identity join을 증명하지 않는다.

### 4.3 공개 metric family

정확한 ID와 view 이름은 registry를 먼저 확정한 뒤 정한다. 한 view에는
하나의 metric만 둔다.

- W-A: registration/enrolment/activation milestone funnel
- W-B: active users, engagement depth, cohort-relative 30/90-day retention
- W-C: coaching delivered/responded/completed, domain-period adherence
- W-D: scoring coverage와 user-disease-period risk trajectory
- Measurement: measuring users/readings. device allocation 분모가 없으면
  participation **rate**라고 부르지 않는다.
- Remote-care readiness: qualifying-day 정의 전에는 `HYPOTHESIS`이며 revenue나
  billing KPI가 아니다.
- 행동→위험 bridge: exposure/outcome window와 최소 표본 수를 명시하고
  causal language를 쓰지 않는다.
- Medical/Financial: 실제 source가 없으면 숫자를 만들지 않고
  `v_bridge_pi_to_kpi`에 gap만 남긴다.

---

## 5. 구현 순서

각 phase의 완료 조건을 통과하기 전에는 다음 phase의 database mutation을
시작하지 않는다.

P1~P5의 grain·reconciliation 완료 조건은 좁은 targeted build로 검증한다.
bare full build나 아직 검토하지 않은 `+` parent/child 확장 selection은 쓰지
않는다.

### P0 — 기존 변경 보존, EL 계약, PII

전체 dbt build 전에 완료한다.

- [x] `git status --short`와 관련 diff를 기록하고 기존 변경을 보존한다.
- [x] 실제 target 수 128과 source 문서의 stale count를 목록화한다.
- [x] 신규 3개 table을 incremental target에서 `full_refresh` target으로 옮긴다.
- [x] full refresh에서도 Loop actor filter가 유지되는지 config test로 고정한다.
- [x] 신규 3개 table의 PK, nullable, timezone, mutation 특성을 문서화한다.
- [x] source PostgreSQL에서 관측된 UPDATE를 근거로
      `create_datetime` watermark에 의존하지 않게 한다.
  - `tb_search_log`: UPDATE 14건 관측
  - `tb_share_log`: UPDATE 28건 관측(2026-08-21 11:32 KST 재측정)
  - `tb_share_info`: UPDATE 0건이지만 작으므로 동일 정책 적용
- [x] 아래 column을 기본 EL 제외 대상으로 추가한다.
  - `tb_search_log.word` — 사용자 free text
  - `tb_share_info.share_key` — access-token-like unique key
  - `tb_share_log.share_key`
  - `tb_share_log.to_user_ip` — 현재 이미 제외됨
  - `tb_share_log.to_user_agent` — fingerprint
  - `tb_share_log.to_user_no` — non-Loop recipient key 포함
- [x] `tb_share_info.target_no`는 polymorphic key이며 `HOME/INVITE`에서는
      user key일 수 있다. `share_type`별 PII/FK 계약 전까지 일반 mart에
      노출하지 않는다.
- [x] raw search term 분석이 정말 필요하면 EL 제외를 되돌리지 말고,
      목적·접근 role·보존기간·topic taxonomy를 먼저 owner 승인으로 정한다.
- [x] 이미 landing된 금지 column은 downstream 의존성이 없음을 확인한 뒤
      별도 review된 cleanup SQL로 제거한다.
- [x] extractor의 `exclude_columns`만 추가해도 기존 landing column이 자동으로
      DROP되지는 않는다는 점을 검증한다.
- [x] `PII_INVENTORY.md`를 128-target 기준으로 다시 생성·검토한다.
- [x] config target 수, actor filter, exclusion을 test로 고정한다.
- [x] offline Python test를 실행한다.

P0 완료 조건:

- [x] 신규 3개 table이 full refresh + Loop actor filter로 선언돼 있다.
- [x] 신규 EL에서 free text, share token, IP, user-agent, 외부 recipient key가
      landing되지 않는다.
- [x] 기존 landing cleanup이 review 가능한 SQL과 검증 쿼리로 남아 있다.
- [x] PII inventory와 target config가 일치한다.
- [x] offline test가 모두 통과한다.

P0에서는 full-refresh target의 landing truncation을 유발하는 실제 EL을 재실행하지
않았다. 위 EL 경계는 config와 extractor의 full-refresh row-filter/exclusion test로
검증했고, 기존 landing은 별도 migration과 post-cleanup catalog query로 정리했다.

### P1 — dbt source, staging, atomic event facts

- [x] `dbt/models/staging/src_iccoli.yml`에 신규 source 3개를 선언한다.
- [x] freshness 대상과 임계치를 table mutation/cadence에 맞게 정한다.
- [x] 아래 staging model을 만든다.
  - `stg_iccoli__tb_search_log`
  - `stg_iccoli__tb_share_info`
  - `stg_iccoli__tb_share_log`
- [x] actor `user_no/from_user_no`를 mapper의 Loop `user_id`로 변환한다.
- [x] raw source serial과 금지 column을 staging output에 노출하지 않는다.
- [x] 원본 timestamptz와 명시적 KST business date를 함께 보존한다.
- [x] source grain-key uniqueness, not-null, actor mapping, share FK와 reconciliation test를
      추가한다.
- [x] mapper-only actor가 canonical SiBC cohort inner join에서 제외되는 차이를
      의도된 reconciliation로 고정한다. 현재 row 수를 영구 상수로 pin하지 않는다.
      P1은 heavy wearable 경로를 참조하던 legacy `dim_user` 대신 동일 population
      source인 `stg_sibc__user_master`를 사용했고, P3에서 `dim_user` FK로 재검증했다.
- [x] 아래 atomic fact를 만든다.
  - `fct_app_search_event`
  - `fct_share_link`
  - `fct_share_interaction_event`
- [x] `share_info`와 `share_log`를 하나의 row-count metric으로 합치지 않는다.
- [x] 기존 `fct_app_action`의 POST/SHARE, SURVEY/SHARE action과 신규 share
      event의 의미 중복을 조사하고 taxonomy에 기록한다.
- [x] source row를 편의상 cross-source dedupe하지 않는다.

P1 완료 조건:

- [x] 모든 신규 fact가 측정된 source unique-index grain
      (`search_log_no`, `share_no`, `share_log_no`)을 만족한다.
- [x] Loop cohort 밖 actor가 mart에 없다.
- [x] 금지 column이 dbt staging/marts schema에 없다.
- [x] share link 생성 수, interacted link 수, interaction event 수가 각각
      독립적으로 재현된다.
- [x] 신규 source → staging → fact row loss가 설명·검증된다.

P1 targeted build evidence, 2026-08-21 12:28 KST:

- exact selection에는 raw heart-rate/wearable detail 경로가 없었다.
- `--threads 1 --fail-fast`: PASS 88, WARN 0, ERROR 0, 12.79초.
- 신규 source freshness 3개가 모두 통과했다.
- fact rows: search 487, share link 1,131, interaction 561.
- retained-cohort share denominator: links 1,131, interacted links 177,
  interaction events 561.
- prohibited staging/mart column query는 0행이었다.

### P2 — core/detail graph와 접근 경계

- [x] dbt model tag와 `selectors.yml`에 `daily_core`,
      `wearable_detail` selector를 추가한다.
- [x] `uv run dbt ls --project-dir dbt --selector daily_core` 결과를 검토한다.
- [x] `daily_core`가 여섯 raw wearable fact와 그 전용 대형 test를 선택하지
      않는지 assert한다.
- [x] `marts`는 core/serving relation만, `marts_detail`은 raw wearable
      relation만 갖게 한다.
- [x] 재사용하는 대형 physical dedupe/intermediate는 일반 BI role이 읽지
      못하는 schema에 둔다.
- [x] `superset_reader`가 `marts`만 읽고 `marts_detail`에는 USAGE/SELECT가
      없는지 grant SQL과 실제 접속으로 검증한다.
- [x] Superset registration은 core relation만 다루게 한다.
- [x] `dbt_project.yml`의 전역 full-table 정책을 model별 정책으로 분리한다.

P2 완료 조건:

- [x] `dbt ls`만으로 core와 detail graph 경계가 명확히 보인다.
- [x] core selector는 약 900만 행 detail fact를 생성하지 않는다.
- [x] detail schema는 일반 Superset/Planning role에서 접근할 수 없다.
- [x] core build와 detail build를 서로 독립적으로 실행할 수 있다.

P2 실행 증거(2026-08-21 KST):

- `daily_core` model 43개에 여섯 source-grain wearable fact가 포함되지
  않았고, 두 전용 대형 test도 0개였다.
- `wearable_detail`은 여섯 fact와 두 전용 test를 포함했다.
- 여섯 0행 legacy detail table을 삭제/재계산 없이 `marts_detail`로,
  47,046행 wearable-day aggregate를 `intermediate_private`로 이동했다.
- `superset_reader` 실제 login으로 `marts.fct_app_search_event` 487행은
  읽었고, `marts_detail`, `intermediate_private`, `staging`, landing 접근은
  모두 `permission denied`였다. 세션은 read-only, KST, 2분 timeout이었다.
- `dbt parse`, selector별 `dbt compile`, P2 selector boundary script가 통과했고
  offline Python baseline은 그대로 95 passed, 32 skipped였다.
- 전체 selector build는 실행하지 않았다. core 전체 build는 P6,
  wearable detail은 P4 storage gate 후의 별도 실행 단위다.

### P3 — dimension, lifecycle, canonical panels

- [x] `dim_user`에서 lifetime 행동으로 만든 `is_observable_*`와
      `is_observable_wearable_and_routine`을 제거한다.
- [x] stable/current profile과 event-time behavior를 분리한다.
- [x] current site를 `bridge_user_site_current` 또는 명시적
      `current_site_id`로 분리한다.
- [x] cohort user가 current approved site를 정확히 하나 갖는지 test한다.
- [x] current site를 과거 fact의 event-time site로 join하지 않는다.
- [x] `fct_user_milestone`을 만든다.
- [x] 실제 source timestamp가 있는 milestone만 등록한다.
  - cohort enrolled
  - iccoli mapped
  - first login
  - first app action
  - first search
  - first share created
  - first share interaction
  - first coaching delivered
  - first measurement
- [x] source로 식별할 수 없는 register/final-register/funnel-end 단계에는
      가짜 날짜나 NULL placeholder row를 만들지 않는다.
- [x] compound cohort table 대신 stable dimension predicate와 versioned named
      cohort definition을 사용한다.
- [x] `fct_measurement`의 grain에 device/source transaction을 포함할지
      재측정하고 conflict test가 unit/device/platform/location 차이를 잡게 한다.
- [x] `fct_user_day`가 staging을 다시 집계하지 않고 canonical atomic facts와
      `fct_wearable_day`를 사용하도록 재작성한다.
- [x] login, action, search, share-created, coaching, measurement, meal,
      wearable channel을 명시한다.
- [x] share interaction은 의미가 확정되기 전까지 sender active-day에 넣지 않는다.
- [x] channel별 load completeness/frontier를 모델링한다.
- [x] empty incremental run도 기록하는 load-run audit가 필요한지 결정한다.
      현재 watermark의 business watermark만으로 전체 DAG 완료를 증명하지 않는다.
- [x] channel이 아직 적재되지 않은 날짜는 false zero로 만들지 않는다.
- [x] `assert_user_day_spine_loses_no_activity`를 routine, wearable,
      integrated analysis, IRS, 신규 app event까지 확장한다.
- [x] `fct_user_month`를 user × calendar/relative month grain으로 만든다.
- [x] partial month와 right-censored cohort를 표시한다.
- [x] active-day, routine denominator pair, measurement-day, qualifying-day를
      같은 월 panel에 보존한다.
- [x] `fct_user_day_wide`에서 lifetime 결과 기반 segment를 제거한다.

P3 완료 조건:

- [x] `dim_user`는 user당 한 행이며 미래 행동정보를 과거에 누출하지 않는다.
- [x] current site와 historical site 의미가 SQL/docs에서 구분된다.
- [x] atomic fact 합계와 user-day 합계가 channel별로 일치한다.
- [x] stale/not-yet-loaded channel이 false zero를 만들지 않는다.
- [x] 월 panel이 denominator와 censoring을 직접 제공한다.

P3 실행 증거(2026-08-21 KST):

- exact model selection을 `dbt ls`로 검토하고 raw heart-rate/detail 경로 없이
  `--threads 1 --fail-fast` targeted build를 실행했다.
- `dim_user`와 `bridge_user_site_current`는 각각 437행이며 Ulsan 393명,
  Jeju 44명, 사용자당 approved current site 정확히 1개 test가 통과했다.
- `fct_user_milestone`은 실제 9개 milestone 2,744행이다. cohort enrollment의
  source DATE에는 timestamp를 만들지 않았고 나머지는 실제 timestamp만 쓴다.
- measurement 재측정에서 user/time/metric 중복 slot 41개와 platform 충돌
  9개를 확인해 source transaction/device/platform/location을 보존했다.
  26,351행 full observation-signature reconciliation이 통과했다.
- `fct_user_day` 81,745행과 `fct_user_month` 2,996행을 생성했다. 11개
  channel의 원자 fact 합계, daily wearable intermediate, state/value 계약,
  grain, FK, denominator/censoring test를 포함한 P3 core test 201개가 통과했다.
- current watermarks는 empty incremental run을 기록하지 않으므로
  `fct_channel_load_status`는 `TARGET_SUCCESS_ONLY`로 명시한다. P7에서
  DAG/run ledger를 구현하기 전에는 `DAG_COMPLETE`라고 부르지 않는다.
- P3 신규 core table은 `superset_reader` SELECT를 상속했고,
  `intermediate_private`와 여섯 `marts_detail` table은 계속 SELECT 불가다.
- P4 전용 `wearable_detail` reconciliation은 아직 0행 detail fact 때문에
  의도적으로 실행 경계 밖에 두었다. P4 storage gate 전 detail build는 하지 않았다.

### P4 — heart-rate 비용 제거와 wearable detail

첫 core build 전에 완료한다. `fct_wearable_day`도 raw heart-rate를 사용하므로
detail fact만 selector에서 빼는 것으로는 충분하지 않다.

- [ ] heart-rate payload dedupe를 physical relation으로 한 번만 계산한다.
- [ ] `fct_wearable_day`, detail fact, attribution, reconciliation이 같은
      deduped relation을 재사용하게 한다.
- [ ] exact duplicate multiplicity를 `source_row_count`로 보존한다.
- [ ] `n_samples = sum(source_row_count)`를 유지한다.
- [ ] 평균은 multiplicity-weighted 결과가 기존 full calculation과 같아야 한다.
- [ ] min/max와 user/date별 일별 집계 동등성을 검증한다.
- [ ] heart-rate dedupe와 detail fact에 30일 lookback incremental 또는
      window-replace 전략을 적용한다.
- [ ] 30일 밖 수정·mapping 변경을 위한 명시적 full-refresh 경로를 남긴다.
- [ ] incremental과 full-refresh 결과의 동등성 test를 추가한다.
- [ ] named consumer가 없는 detail fact는 daily build에서 제외한다.
- [ ] 분석가가 detail을 실행할 때의 Azure monitor, threads=1, stop 절차를
      문서화한다.

P4 완료 조건:

- [ ] 같은 약 900만 행 `GROUP BY`가 model/test마다 반복되지 않는다.
- [ ] core build가 `fct_wearable_heartrate` 전체를 재생성하지 않는다.
- [ ] 일별 wearable 값과 source-row reconciliation이 기존 정의와 일치한다.
- [ ] core/detail의 permanent size, runtime, temp delta를 따로 측정할 수 있다.

### P5 — W-A/B/C/D semantic layer

- [ ] metric registry를 추가하고 공개 metric을 모두 등록한다.
- [ ] active event taxonomy를 versioning한다. login, action, search,
      share-created, share-interaction을 임의로 합치지 않는다.
- [ ] W-A는 동일 모집단이 milestone을 통과하는 event funnel로 계산한다.
- [ ] W-B retention은 동일 cohort 정의와 censoring 규칙을 사용한다.
- [ ] 30-day와 90-day를 서로 다른 denominator로 한 곡선에 그리지 않는다.
- [ ] W-C는 delivered, responded, completed를 분리한다.
- [ ] W-C의 event-weighted와 user-weighted 결과를 별도 metric으로 둔다.
- [ ] domain adherence에는 week/month 축과 user 수·delivered 수를 함께 둔다.
- [ ] W-D는 user × disease × period 대표값을 먼저 만든 뒤 사용자 가중으로
      집계한다.
- [ ] scoring coverage 분모는 해당 period까지 가입하고 관측 가능한 cohort다.
- [ ] 월중 한 번이라도 high-risk였던 union과 month-end/latest risk를
      혼동하지 않는다.
- [ ] IRS 이동은 `DERIVED`/validation으로 표시하고 임상 효과라고 쓰지 않는다.
- [ ] 행동→위험 bridge에는 exposure window, outcome window, 최소 표본 수를
      명시한다.
- [ ] 기존 metric view를 keep/replace/retire 표로 기록한다.
- [ ] metric이 완전히 0행이어도 기존 not-null test가 통과하는 문제를 막는
      non-empty/fresh-period test를 추가한다.
- [ ] 모든 공개 metric/view에 `data_as_of` 또는 함께 조회할 freshness
      relation을 제공한다.

P5 완료 조건:

- [ ] 모든 metric이 entity, time, aggregation, denominator를 가진다.
- [ ] denominator·eligibility·censoring이 SQL과 registry에서 일치한다.
- [ ] `OBSERVED`, `DERIVED`, `HYPOTHESIS`, `ROADMAP`이 화면에서 구분된다.
- [ ] source가 없는 Medical/Financial KPI는 숫자가 아니라 bridge gap으로 남는다.
- [ ] 대표 metric이 non-empty/freshness test를 통과한다.

### P6 — 안전 복구, 검증, Superset

P0~P5 완료 후에만 database build를 실행한다.

- [ ] 다섯 source의 EL 완료 상태를 확인한다.
- [ ] 필수 source freshness를 hard gate로 확인한다.
- [ ] Azure Monitor storage used/free를 build 직전에 기록한다.
- [ ] 80% stop line을 적용한다.
- [ ] 아래 명령으로 core를 단일 스레드 실행한다.

```bash
source setup_env.sh
uv run dbt source freshness --project-dir dbt
uv run dbt build --project-dir dbt --selector daily_core --threads 1 --fail-fast
```

- [ ] 실행 전·peak·후 Azure storage를 기록한다.
- [ ] `pg_database_size`와 `pg_stat_database.temp_bytes`의 전후 delta를 기록한다.
- [ ] model/test별 runtime과 실패 node를 기록한다.
- [ ] dims → atomic facts → panels → metric views row count를 기록한다.
- [ ] grain, FK, PII, funnel, user-day, risk, wearable reconciliation을 확인한다.
- [ ] graph가 바뀌므로 “388개 통과”를 목표로 삼지 않는다. 현재 graph의
      전체 선택 node가 green인지 확인한다.
- [ ] core 통과 후 필요한 경우에만 detail을 별도 계측 실행한다.

```bash
uv run dbt build --project-dir dbt --selector wearable_detail --threads 1 --fail-fast
```

- [ ] full live Python suite를 실행한다.
- [ ] dbt docs를 생성하고 lineage를 검토한다.
- [ ] Superset dataset을 새 core mart에 맞게 재등록한다.
- [ ] `superset_reader`가 detail/staging/landing을 읽지 못하는지 실제
      connection으로 검증한다.
- [ ] W-A/B/C/D 대표 쿼리와 chart를 smoke test한다.
- [ ] 폐기·rename된 metric을 참조하는 기존 dashboard를 함께 갱신한다.
- [ ] dashboard에 마지막 성공 EL/build 시각과 evidence status를 표시한다.

P6 완료 조건:

- [ ] current Python test suite가 모두 green이다.
- [ ] `daily_core`의 model/test가 모두 green이다.
- [ ] core storage peak와 runtime 기준선이 기록돼 있다.
- [ ] Superset 대표 chart가 현재 extraction 기준 data를 반환한다.
- [ ] raw detail·PII가 일반 BI role에 노출되지 않는다.
- [ ] detail build 실패가 daily core의 성공 상태를 훼손하지 않는다.

### P7 — 자동 운영과 인수인계

mart correctness와 core build 비용이 검증된 뒤 진행한다.

- [ ] 5개 EL이 모두 성공한 뒤 transform이 시작되는 실제 dependency를 만든다.
- [ ] 01:00/02:00 고정 시각 차이를 dependency로 사용하지 않는다.
- [ ] 필수 source freshness 실패가 transform을 차단하게 한다.
- [ ] build 직전 Azure storage preflight를 실행한다.
- [ ] transform DAG가 `daily_core`, `--threads 1`, `--fail-fast`를 사용하게 한다.
- [ ] resource/storage 실패에 대한 blind full-build retry를 제거한다.
- [ ] `max_active_runs=1`을 유지한다.
- [ ] empty incremental run까지 포함한 EL run ledger 또는 동등한 완료 증명을
      구현한다.
- [ ] scheduler가 실행될 Azure 위치와 service identity를 확정한다.
- [ ] Airflow metadata DB의 durable 위치, backup, 계정/secret rotation을
      확정한다. 창민님의 로컬 환경을 운영 구성요소로 두지 않는다.
- [ ] 영구 운영자와 실패 알림 수신자를 서면으로 지정한다.
- [ ] 영문 `RUNBOOK.md`에 storage 사고 대응, 수동 core 재실행, detail 실행
      절차를 기록한다.
- [ ] `HANDOVER.md`, `HOWTO.md`, decision log, model README, target 수가
      들어간 문서를 새 구조에 맞게 갱신한다.
- [ ] Azure endpoint 분리는 아래 trigger 중 하나가 성립할 때 runbook으로
      재검토한다.
  - storage 사용률 7일 이상 70% 초과
  - 90일 이내 80% 도달 예상
  - 정상 core build가 운영 DB latency/IOPS/CPU에 유의미한 영향
  - 반복 증설 필요
  - DW의 보안·backup·DR 요구가 운영 DB와 달라짐

P7 완료 조건:

- [ ] local machine 없이 daily EL → freshness → core transform이 실행된다.
- [ ] 실패 알림에 source, freshness, storage, dbt node가 포함된다.
- [ ] 후임자가 runbook만으로 실패를 진단하고 안전하게 재실행할 수 있다.
- [ ] metadata DB와 Superset app DB의 backup/restore 책임자가 정해져 있다.

---

## 6. 구현 전에 owner 확인이 필요한 의미 계약

아래 결정이 없어도 P0~P4의 구조·안전 작업은 진행할 수 있다. 해당 metric의
공개만 보류한다.

| 결정 | 미확정 시 안전한 기본값 |
|---|---|
| “activation”으로 인정할 최초 사건 | `fct_user_milestone`에는 원시 milestone만 저장하고 W-A rate 공개 보류 |
| 30/90-day retention의 active event와 window | 동일 cohort·censoring 계약 확정 전 retention 공개 보류 |
| `tb_share_log`와 `point_call_yn`의 정확한 업무 의미 | 중립적 interaction event로 저장하고 open/success라고 부르지 않음 |
| raw search term 분석 필요 여부 | EL 및 일반 mart에서 제외 |
| external recipient 분석 필요 여부 | raw recipient key를 저장하지 않음 |
| `remote_care qualifying day` 정의 | `HYPOTHESIS`, revenue/billing 계산 금지 |
| device measurement eligibility 분모 | 사용자 수/reading 수만 제공하고 adherence rate 금지 |
| historical site attribution | upstream unlink→insert·변경시각 계약 전까지 금지 |
| Medical/Financial KPI | encounter/claim source와 grain 검증 전 `ROADMAP` |
| scheduler/운영 owner | 자동 운영 시작 금지 |

---

## 7. 전체 완료 기준

아래를 모두 만족해야 “marts 복구 완료”라고 부른다.

- [x] 기존 uncommitted 작업이 보존되고 하나의 review 가능한 migration으로
      정리돼 있다.
- [x] 신규 search/share EL이 full refresh이며 PII contract를 지킨다.
- [x] 신규 atomic fact의 grain과 세 가지 share denominator가 검증된다.
- [x] `dim_user`에 미래 행동을 과거로 누출하는 lifetime 결과 flag가 없다.
- [x] dense user-day에서 관측된 zero와 미적재 unknown이 구분된다.
- [x] current site가 historical attribution으로 사용되지 않는다.
- [ ] W-A/B/C/D metric contract가 git에 있고 evidence status가 보인다.
- [ ] Medical/Financial 미보유 데이터가 숫자로 위장되지 않는다.
- [x] daily core가 raw wearable detail full rebuild에 의존하지 않는다.
- [x] core/detail schema와 database-role 경계가 실제 접속으로 검증된다.
- [ ] Python tests, dbt tests, storage 계측, Superset smoke test가 모두 통과한다.
- [ ] local machine 없이 운영할 scheduler·metadata DB·owner·runbook이 정해져 있다.

---

## 8. 다음 세션의 첫 작업

1. 이 문서의 `0`과 `P4`를 다시 읽는다.
2. `git status --short`와 P0/P1 diff를 확인하고 보존한다.
3. Azure Monitor storage 사용률을 확인하고 70%/80% stop line을 적용한다.
4. 현재 heart-rate staging/detail/daily SQL과 exact duplicate multiplicity를
   다시 측정하되, 대형 build 전에는 읽기 범위와 예상 비용을 고정한다.
5. 재사용 physical heart-rate dedupe와 30일 window-replace 전략을 구현한다.
6. daily/detail/attribution/reconciliation이 같은 dedupe relation을 쓰게 한다.
7. incremental/full-refresh 및 multiplicity-weighted daily 동등성을 검증한다.
8. named detail consumer가 없으면 detail build는 실행하지 않는다.
9. **P0~P5가 끝나기 전에는 전체 dbt build를 실행하지 않는다.**
