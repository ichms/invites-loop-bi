# invites-loop-bi

Invites Loop의 다섯 PostgreSQL 운영 소스에서 데이터를 추출해 warehouse landing에
적재하고, dbt로 분석용 모델과 지표를 만드는 OLAP ELT 프로젝트입니다. Python
코드는 행을 객체나 dataframe으로 만들지 않고 PostgreSQL `COPY` 스트림을 그대로
전달합니다.

## 현재 상태 — 2026-08-21 KST

이 리포지토리는 정상 운영 상태가 아니라 **W-first mart 재설계와 안전 복구를
진행 중**입니다. 실행 순서와 gate의 유일한 기준은 [`todo.md`](todo.md)입니다.

- extraction target은 128개입니다: iccoli 37, ichms 16, sibc 36, irs 5,
  discovery 34.
- `stg_meta.watermarks` 128개 행은 모두 `SUCCESS`지만, 이것만으로 전체 DAG 실행
  완료나 channel freshness가 증명되지는 않습니다.
- P3 targeted build로 dimension, atomic fact, milestone, user-day 81,745행,
  user-month 2,996행을 복구했습니다. 전체 `daily_core` build는 아니며,
  `marts_detail`의 raw wearable fact 6개는 아직 0행입니다. Superset은
  refresh/대표 chart acceptance를 하지 않았으므로 기존 출력은 아직 인용 가능한
  운영 지표가 아닙니다.
- 과거의 `dbt build 388/388`, `pytest 125/125`는 현재 acceptance baseline이
  아닙니다. 현재 offline test 기준선은 95 passed / 32 skipped이며 live suite는
  다시 실행하지 않았습니다.
- EL과 dbt는 모두 수동입니다. Airflow schedule은 코드에 선언돼 있지만 실제
  scheduler가 배포되거나 정상 운전된 적은 없습니다.
- P0~P3는 완료됐습니다. `daily_core`/`wearable_detail` selector,
  private/detail schema, materialization, grant와 registration 경계가 구현·검증됐고,
  dimension/lifecycle/canonical panel도 targeted 검증됐습니다. 다음 단계는 P4
  reusable heart-rate dedupe와 wearable detail입니다.

### 지금 실행하면 안 되는 것

P0~P5가 끝날 때까지 다음 작업은 금지됩니다.

- selector 없는 `uv run dbt build --project-dir dbt`
- `transform_dbt_build` 활성화 또는 scheduler 시작
- Superset 전체 marts dataset 자동 재등록
- 추가 landing `TRUNCATE`, 삭제, 수동 watermark 삭제
- Azure storage 확인 없는 wearable detail/heart-rate build
- current site를 과거 event 당시 site로 해석하는 분석

현재 transform DAG는 freshness 실패를 무시하고 전체 graph를 threads=4로 실행한
뒤 실패 시 재시도할 수 있습니다. 안전 복구 전에는 실행하지 마세요.

## 목표

이번 재설계는 실제로 관측 가능한 Wellness 데이터를 중심으로 작고 안전한 daily
core를 만드는 작업입니다.

```text
W-A 획득·활성
  → W-B 참여·잔존
    → W-C 행동수행
      → W-D 위험점수 이동
```

Wellness 지표는 근거 상태를 `OBSERVED`, `DERIVED`, `HYPOTHESIS`, `ROADMAP`으로
명시합니다. admission, LOS, readmission, claim, billing처럼 source가 없는
Medical/Financial 지표는 숫자를 만들지 않고 gap register에만 남깁니다. 앱 행동이나
IRS 변화도 임상 효과·인과 효과라고 부르지 않습니다.

목표 물리 구조는 다음과 같습니다.

```text
operational PostgreSQL sources
  → stg_<system>                 EL landing
  → staging                     cast, dedupe, key translation, PII blocking
  → private physical intermediate
       ├─→ marts                dimensions, facts, panels, thin metrics
       │    └─→ Superset        core/serving relations only
       └─→ marts_detail         source-grain wearable observations
                                analyst-only; excluded from daily core and Superset
```

`daily_core`와 `wearable_detail` selector, `intermediate_private`,
`marts_detail` 경계는 P2에서 구현됐습니다. metric registry와 W-A/B/C/D
serving layer는 아직 목표 상태입니다.

## 핵심 불변식

### EL

- 실행 순서는 `extract → load → commit`입니다.
- watermark는 staging commit 뒤에만 이동합니다. 실패 시 같은 window를 재생합니다.
- 첫 incremental run은 predicate 없이 전체 table을 읽어 watermark가 NULL인 행도
  포함합니다.
- 선언된 full-refresh target은 PK 유무와 무관하게 transaction 안에서 truncate 후
  insert합니다. 그 외 PK incremental table은 upsert하고, PK 없는 incremental
  table은 추출 window를 삭제한 뒤 재삽입합니다.
- source schema는 catalog에서 introspect하며 upstream 신규 column은 landing에
  자동 추가됩니다. 이 때문에 신규 column log는 PII review trigger입니다.
- `exclude_columns`와 `row_filter`는 EL 경계의 정책입니다. 제외된 데이터를 되살리는
  일은 단순 model 변경이 아니라 owner 승인이 필요한 정책 변경입니다.

### dbt와 지표

- 모든 fact는 grain을 SQL header에 선언하고 그 grain의 uniqueness를 테스트합니다.
- `fct_user_day`는 zero day를 포함하는 dense user × day panel입니다. 단, source가
  stale하거나 아직 적재되지 않은 channel의 0은 무활동이 아니라 unknown입니다.
- panel 상한은 `current_date`가 아니라 source/channel observation frontier입니다.
- IRS/IRS+/LRS/MRS/PRS는 1~100 rank입니다. 서로 더하거나 빼서 원인 기여도를
  만들 수 없습니다.
- current site는 current-state filter일 뿐입니다. 알려진 in-place flip의 과거
  값과 전환시각이 없으므로 historical/as-of site attribution은 금지합니다.
- wearable row count는 backfill 때문에 extraction date에 따라 변합니다. 숫자를
  인용할 때 extraction date를 함께 적습니다.

## 안전한 시작

Python 3.13 이상과 [uv](https://docs.astral.sh/uv/)를 사용합니다.

```bash
uv sync
cp setup_env.sh.example setup_env.sh
source setup_env.sh
```

`setup_env.sh`는 실제 credential을 담으므로 Git에 올리지 않습니다. 현재 phase에서
안전한 확인 명령은 아래와 같습니다.

```bash
git status --short
git diff -- src/invites_loop_bi/config/iccoli_targets.py
git diff -- tests/extract/test_config_targets.py
INVITES_LOOP_BI_TEST_OFFLINE=1 uv run pytest
uv run dbt parse --project-dir dbt
uv run dbt compile --project-dir dbt
```

selector가 구현된 뒤에는 build 전에 선택 graph부터 확인합니다.

```bash
uv run dbt ls --project-dir dbt --selector daily_core
uv run dbt ls --project-dir dbt --selector wearable_detail
```

P0~P5 동안 허용되는 database build는 graph를 먼저 확인한 **명시적인 소형 model
selection**뿐입니다. `--threads 1 --fail-fast`를 사용하고, 검토하지 않은 `+`
확장은 쓰지 않습니다. 최초 전체 `daily_core` build는 P6의 freshness·Azure storage
gate 뒤에만 실행합니다.

## 연결 구조

| Source system | Database | Airflow connection id |
|---|---|---|
| `iccoli` | `iccoli`, schema `public` | `iccoli_db_conn` |
| `ichms`, `sibc`, `irs`, `discovery` | `invites_loop` | `invites_loop_db_conn` |
| warehouse | `invites_dw` | `olap_db_conn` |

환경변수는 `AIRFLOW_CONN_*`과 `DBT_PG_*`를 사용합니다. source connection은
read-only이고 warehouse transaction은 autocommit을 끕니다. source와 warehouse의
session timezone은 맞아야 합니다.

## 리포지토리 구조

```text
dags/                         Airflow DAG declarations; not an operating scheduler
src/invites_loop_bi/
  config/                     128 declarative extraction targets
  extract/                    COPY extraction, introspection, watermarks
  load/                       temp table, COPY, merge
  pipeline.py                 real CLI entry point
dbt/
  models/staging/             current dbt staging layer
  models/marts/               P3 core models plus unaccepted legacy metric views
  tests/                      grain and reconciliation tests
deploy/superset/              local Superset stack and reproducible dashboard tooling
scripts/                      reviewed one-off migration/cleanup SQL
tests/                        offline and live Python tests
```

실제 CLI entry point는 `src/invites_loop_bi/pipeline.py`입니다.

## 문서 지도

| 문서 | 역할 |
|---|---|
| [`todo.md`](todo.md) | 현재 실행 계약, phase gate, 완료 조건 |
| [`AGENTS.md`](AGENTS.md) | 안정적인 아키텍처·개발 규칙 |
| [`INVITES_LOOP_BI_DECISION_LOG.md`](INVITES_LOOP_BI_DECISION_LOG.md) | 현재 결정과 근거 |
| [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) | 측정이 과거 가정을 뒤집은 기록; 실행 계획 아님 |
| [`PII_INVENTORY.md`](PII_INVENTORY.md) | landing PII snapshot, retention/exclusion 계약 |
| [`HOWTO.md`](HOWTO.md) | 안전한 변경·검증·Superset 절차 |
| [`HANDOVER.md`](HANDOVER.md) | 복구 상태, 책임, owner 결정 목록 |

`/docs`, `/data`, `/analysis`는 `.gitignore`로 제외된 로컬 archive입니다.
`docs/business_intelligence`는 과거의 사고 과정과 외부 리서치를 보존하지만,
그 안의 `LOCKED`, `FROZEN`, `SSOT` 표기나 수치는 현재 권위가 아닙니다. 재사용할
원칙만 이 표의 tracked 영문 문서로 선별 승격하고, exact duplicate, checkpoint,
현재 구조와 충돌하는 구형 AI 계획서는 제거합니다. 그 밖의 archive는 수정하지
않습니다.

## 변경 규칙

- extraction table 추가는 해당 `config/<system>_targets.py`에서 합니다.
- 직접 식별자, free text, token, 외부 사용자 key를 다시 보존하려면 먼저 목적,
  접근 role, 보존기간, 삭제 절차를 승인받아야 합니다.
- mart 변경은 [`HOWTO.md`](HOWTO.md)의 targeted workflow를 따릅니다.
- 별도 요청이 없으면 commit, push, deploy하지 않습니다.
