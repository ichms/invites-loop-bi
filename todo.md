# TODO — 다음 작업 시작점

최종 갱신: **2026-08-20**

아키텍처는 `AGENTS.md`, 결정의 근거는
`INVITES_LOOP_BI_DECISION_LOG.md`, 측정 결과가 기존 결정을 뒤집은 기록은
`IMPLEMENTATION_PLAN.md` §3, 인수인계 상태는 `HANDOVER.md`를 본다.

이 문서는 현재 상태와 다음 작업의 우선순위를 기록한다. 과거 작업의 상세한
배경은 위 문서와 git 이력에 남기고, 여기에는 다음 사람이 실제로 판단하고
실행하는 데 필요한 사실만 유지한다.

---

## 0. 현재 상태

Extract → Load → dbt Transform → marts → metric views → Superset까지 모두
구현돼 있다. 다만 **모든 실행은 아직 수동**이며, 운영 스케줄러는 배포되지
않았다.

마지막으로 확인된 정상 상태는 2026-08-13의 `dbt build` **388/388** 및
`pytest` **125/125**다. 이 숫자는 현재 상태를 의미하지 않는다. 2026-08-20
저장공간 사고 대응 중 marts 데이터가 `TRUNCATE`됐으므로, 현재 운영 상태는
**복구 build 및 전체 검증 전**이다.

| 구성요소 | 현재 상태 |
|---|---|
| `extract/`, `load/`, `pipeline.py` | 구현 및 실제 DB 검증 완료 |
| dbt staging | 23개 SQL 모델. 대부분 view이며 wearable day만 대형 입력을 일별로 축약한 table |
| dbt marts | 6개 dim, 12개 핵심 fact, `fct_user_day_wide`, 7개 `v_pi_*`, 1개 bridge view |
| dbt 검증 | 마지막 정상 build 388/388; 8월 20일 사고 후 재검증 필요 |
| Python 검증 | 마지막 `pytest` 125/125 |
| Superset | 6.1.0 로컬 배포 및 `superset_reader` 검증 완료 |
| Superset dataset | 19개가 마지막으로 등록·검증됨. 현재 marts 전체 relation과 재동기화 필요 |
| Airflow | 5개 ELT DAG와 `transform_dbt_build` 작성 완료, 운영 스케줄 실행 이력 없음 |
| PII | inventory와 1차 cleanup 완료; R-5 table scope, R-6 일부, R-7/R-8 열림 |
| 운영 책임자 | 창민님이 임시 담당. 영구 담당자 Q-04는 보류 상태 |

### 이번 작업의 순서

1. marts를 단일 스레드로 복구하고 저장공간 peak를 측정한다.
2. dbt 실행 전 저장공간 가드와 실패 정책을 추가한다.
3. 심박수 모델의 반복 대형 집계를 제거한다.
4. 자동 운영 전에 EL 완료 → freshness 통과 → dbt 실행의 실제 의존성을 만든다.
5. 창민님 결정 항목과 외부 의존 항목을 각각 닫는다.

---

## 1. 2026-08-20 저장공간 사고

### 1.1 확인된 사실

- 8월 14일 기준 Extraction과 Load를 수행한 뒤, 8월 20일 dbt 변환을
  실행하던 중 Azure PostgreSQL이 저장공간 보호를 위해 read-only 모드로
  전환됐다.
- 로그상 09:48 KST경 wearable day 집계와 여러 심박수 view 테스트가
  `threads: 4`로 동시에 실행됐다.
- 처음 관측된 DB 오류는 dbt가 이전 테이블을 제거하는 단계의
  `cannot execute DROP TABLE in a read-only transaction`이었다. `DROP`이
  원인이 아니라, 그 전에 서버가 보호 모드로 전환된 결과다.
- 서버는 실행 전부터 128GB 용량 임계치에 근접해 있었다. 당시 주요 DB의
  파일 크기 합은 약 109GB였고, `invites_dw`의 상시 점유는 약 5.44GB,
  전체의 5~6%였다.
- 서버 시작 시점인 2026-08-16 이후 `invites_dw`의 `temp_bytes` 누적치는
  약 26GB였다. 이는 동시 최대 사용량이 아니라 누적값이지만, 대형 집계가
  반복해서 디스크로 spill됐다는 증거다.
- 확인 당시 설정은 `work_mem=4MB`, `temp_file_limit=-1`,
  `max_parallel_workers_per_gather=2`였다.
- 응급 조치로 marts 데이터를 `TRUNCATE`했다. 이는 일부 공간을 즉시
  회수했지만 서버 점유의 대부분이 DW가 아니므로 근본 해결은 아니다.
- Azure 담당자가 저장공간을 128GB에서 256GB로 증설했다. 동일한 약
  109GB를 기준으로 현재 점유율은 대략 43%이므로 단기 여유는 충분하다.
- Azure Database for PostgreSQL Flexible Server는 일반적으로 storage 사용률
  95% 이상 또는 남은 공간 5GiB 미만에서 read-only 보호 모드로 전환될 수
  있다. 그래서 dbt 차단선은 Azure의 최종 보호선보다 충분히 앞에 둬야 한다.

### 1.2 근본 원인과 직접 촉발 요인

**근본 원인:** 운영 DB와 DW가 같은 PostgreSQL endpoint의 저장공간, I/O,
CPU를 공유하는 상황에서 서버가 이미 저장공간 임계치에 가까웠다. 별도
database는 논리적 경계를 주지만 물리 자원을 격리하지 않는다.

**직접 촉발 요인:** dbt가 약 901만 landing 심박수 행을 대상으로 큰
`GROUP BY`를 여러 번 동시에 수행했다. `stg_discovery__lifelog_wearable_heartrate`
는 view이므로 staging 테스트, fact 생성, attribution 및 reconciliation
테스트가 참조할 때마다 집계가 다시 펼쳐진다. 이어서 약 888만 행의
`fct_wearable_heartrate`도 매 build마다 완전 재생성된다.

따라서 “dbt만 없었으면 문제가 없었다”도, “DW가 서버를 채웠다”도 정확하지
않다. dbt가 장애 시점을 앞당겼지만, 기존 운영 데이터 증가만으로도 가까운
시일 내 같은 보호 모드가 발생할 상태였다.

### 1.3 2026-08-20 확정 결정 — endpoint 유지

- 운영 DB와 `invites_dw`는 당분간 현재 endpoint에 유지한다.
- 별도 staging endpoint로 OLAP를 이전하지 않는다.
- Azure 담당자가 향후 별도 endpoint 분리를 위한 migration runbook을
  작성한다.
- 지금은 데이터 이동 프로젝트를 시작하지 않고, 현재 endpoint에서 dbt의
  transient storage와 동시 부하를 줄인다.
- 이 결정을 `INVITES_LOOP_BI_DECISION_LOG.md`에 신규 결정으로 동기화해야
  한다. 제안 번호는 **D-33**이다.

### 1.4 endpoint 분리 재검토 트리거 — Azure 담당자와 합의 필요

아래 중 하나를 만족하면 runbook을 꺼내 분리를 재검토한다.

- 저장공간 사용률이 7일 이상 70%를 초과한다.
- 최근 성장률로 보아 90일 이내 80%에 도달할 전망이다.
- 정상 dbt 실행이 운영 DB의 latency, IOPS 또는 CPU를 유의미하게 악화시킨다.
- dbt 실행을 위해 서버 용량을 반복 증설해야 한다.
- DW의 보안, 백업, 장애복구 또는 유지보수 정책이 운영 DB와 달라진다.

용량이 넉넉하더라도 운영 DB 성능 간섭이 확인되면 분리 사유가 성립한다.

---

## 2. P0 — 다음 전체 dbt 실행 전

### 2.1 marts 복구와 기준선 측정

다음 복구 build는 평소 실행이 아니라 **기준선 계측 작업**으로 취급한다.

1. EL 결과와 `dbt source freshness`를 먼저 확인한다.
2. `dbt build --project-dir dbt --threads 1 --fail-fast`로 실행한다.
3. 실행 전, 실행 중 peak, 실행 후의 Azure storage used/free와 DB별 크기를
   기록한다.
4. 심박수 staging/fact/test별 실행시간과 temp 사용량을 별도로 기록한다.
5. 전체 388/388 통과를 확인한다.
6. marts row count와 wearable reconciliation을 확인한다.
7. Superset의 기존 dataset과 현재 marts relation 차이를 확인한다. 원시
   wearable fact의 노출 범위를 결정하기 전에는 전체 자동 등록을 실행하지
   않는다.
8. 기존 PI dashboard의 대표 쿼리가 실제 행을 반환하는지 확인한다.

복구가 끝나기 전에는 과거의 388/388을 현재 정상 상태의 증거로 인용하지
않는다.

### 2.2 저장공간 사전 가드

초기 안전선은 다음과 같이 둔다. 한 번의 정상 build peak를 측정한 뒤
수치로 다시 정한다.

| 사용률 | 동작 |
|---|---|
| 70% 미만 | 정상 실행 |
| 70% 이상 | 경고하고 예상 build peak를 확인 |
| 80% 이상 | 신규 dbt build를 시작하지 않음 |

256GB의 80%에서 차단하면 약 51GB의 여유가 남는다. 최종 차단선은
`보호모드 임계치 - max(정상 build peak의 2배, 운영 여유분)`이라는 원칙으로
정한다.

가능하면 Azure Monitor의 서버 전체 storage 지표를 사용한다. SQL의
`pg_database_size()` 합은 DB relation 크기 비교에는 유용하지만 Azure가
관리하는 전체 파일시스템 사용량과 완전히 같지는 않다.

### 2.3 실패 정책

- 현재 `transform_dbt_build`의 `retries=1`은 저장공간 또는 리소스 장애에도
  10분 뒤 전체 build를 다시 건다. 저장공간 가드가 생기기 전까지
  **`retries=0`으로 변경**한다.
- 저장공간 부족은 자동 재시도 대상이 아니다. 용량 확인과 원인 제거 뒤
  사람이 재실행한다.
- build 일부만 성공한 상태를 정상으로 간주하지 않는다. 전체 build와
  reconciliation이 통과해야 복구 완료다.
- Azure 관리자와 협의해 dbt 역할의 `temp_file_limit` 적용 가능 여부를
  확인한다. 값은 정상 peak 측정 전에는 추측으로 정하지 않는다.
- `work_mem`을 먼저 크게 올리지 않는다. 쿼리 하나의 spill은 줄 수 있지만
  worker × sort/hash 연산 수만큼 메모리가 곱해져 다른 장애를 만들 수 있다.
  먼저 `threads=1` 기준선을 측정한다.

### 2.4 사고 대응 runbook

`HANDOVER.md`에서 열려 있는 `RUNBOOK.ko.md`에 다음 순서를 기록한다.

1. 신규 EL/dbt 실행 중단
2. Azure storage와 DB별 점유 확인
3. 실행 중인 대형 쿼리 및 build run 식별
4. 필요 시 Azure 증설 또는 문제 작업 중단
5. 재생성 가능한 marts 정리는 최후 수단으로만 수행
6. 단일 스레드 복구 build
7. dbt 테스트, reconciliation, Superset smoke test
8. 사고 시각, peak, 조치, 재발 방지책 기록

`TRUNCATE marts`를 기본 대응으로 만들지 않는다. landing과 source를 지우는
절차는 이 runbook에 포함하지 않는다.

---

## 3. P1 — 반복 대형 집계 제거

### 3.1 심박수 dedupe를 한 번만 계산

현재 구조:

1. 약 901만 landing 행을 staging view가 `GROUP BY`한다.
2. staging generic tests가 같은 view를 반복 평가한다.
3. `fct_wearable_heartrate`가 view를 다시 평가해 약 888만 행 table을 만든다.
4. fact tests와 두 custom reconciliation test가 다시 큰 relation을 읽는다.
5. `stg_discovery__lifelog_wearable_day`도 원본 심박수 행을 일별 집계한다.

목표 구조:

- 심박수 payload dedupe 결과를 물리 relation으로 한 번 계산한다.
- `fct_wearable_heartrate`, wearable day, attribution, reconciliation이 그
  결과를 재사용한다.
- wearable day가 dedupe relation을 사용할 때 exact duplicate의 multiplicity를
  잃지 않는다. `n_samples`는 `sum(source_row_count)`, 평균은
  `sum(heartrate_count * source_row_count) / sum(source_row_count)`로 계산하고
  min/max는 기존 값과 같아야 한다.
- grain, FK, row-count 보존 테스트는 유지한다. 단지 같은 `GROUP BY`를
  테스트마다 다시 만들지 않는다.
- 변경 전후 결과가 완전히 같은지 row count, `source_row_count` 합,
  user/date별 집계로 검증한다.

staging table 하나의 상시 점유는 늘지만, 현재 256GB 환경에서는 약 900만
행을 테스트마다 임시로 재집계하는 것보다 예측 가능하고 안전한 trade-off다.

### 3.2 Q-05 재개방 — 심박수 계열만 제한적 incremental

기존 결정은 “전체 build가 약 15분을 넘기 전에는 모든 marts를 full table로
재생성한다”였다. 이 기준은 당시 측정된 작은 모델을 전제로 했고, 8월 20일
장애가 그 전제를 깨뜨렸다.

새 기준은 실행시간만이 아니다.

- transient storage peak
- 동일 endpoint의 운영 DB에 주는 I/O와 CPU 영향
- 반복 scan 및 정렬 횟수
- 늦게 도착하는 데이터의 정정 가능성
- 후임자가 이해하고 복구할 수 있는 복잡도

모든 모델을 incremental로 바꾸지 않는다. 우선 심박수 dedupe와
`fct_wearable_heartrate`만 대상으로 한다.

- 이미 측정된 30일 lookback window를 재사용한다.
- window 안의 기존 행을 지우고 현재 landing 결과로 다시 삽입한다.
- mapping 변경이나 30일 밖 수정에 대비해 정기 또는 수동 full refresh 경로를
  유지한다.
- incremental과 full refresh 결과의 동등성 테스트를 추가한다.
- 작은 dim/fact는 full rebuild를 유지한다.

### 3.3 동시성

- 복구와 첫 최적화 검증은 `threads=1`로 수행한다.
- 정상 build peak와 운영 DB 영향이 확인된 뒤에만 `threads=2`를 시험한다.
- `threads=4`로의 복귀는 단순 실행시간 단축이 아니라 peak storage와 운영
  영향까지 비교한 측정 결과가 있을 때만 허용한다.

---

## 4. P1 — 자동 운영 전에 고칠 orchestration

현재 5개 ELT DAG는 01:00 KST, transform DAG는 02:00 KST를 선언하지만,
이는 실제 완료 의존성이 아니라 시간 차이일 뿐이다. EL이 한 시간을 넘기거나
일부 source만 실패해도 transform이 시작될 수 있다.

또한 `transform_dbt_build.py`는 `dbt source freshness ... || true`로
freshness 실패를 무조건 무시한다. D-01의 “조용한 오답보다 큰 실패” 원칙과
맞지 않는다.

자동 운영 전에 다음을 구현한다.

- 5개 EL 작업이 모두 성공한 뒤 transform이 실행되도록 실제 dependency를
  만든다.
- 필수 source의 freshness error는 transform을 차단한다.
- 단순 warn과 error를 구분한다. 변경이 적은 정상 테이블을 일괄 실패시키지
  않는다.
- `max_active_runs=1`은 유지해 두 build가 같은 marts를 동시에 쓰지 못하게
  한다.
- storage preflight를 build 직전 실행한다.
- 실패 알림에 source freshness, Azure storage, 실패한 dbt node를 포함한다.

### Q-13을 둘로 분리

- **Q-13A — Airflow/scheduler 운영 위치:** 데이터 신선도와 무인 운영을
  막고 있으므로 실제 open item이다.
- **Q-13B — Superset production hosting:** 로컬 검증과 모델링을 막지 않으므로
  계속 보류할 수 있다.

대시보드 숫자를 운영 수치로 취급하기 전에는 Q-13A가 닫혀야 한다. 그전까지
대시보드에는 마지막 성공 extraction/build 시각을 함께 표시한다.

---

## 5. 창민님 결정이 필요한 항목

### 5.1 저장공간 사고와 직접 관련된 결정

| 결정 | 선택지가 바꾸는 것 | 권고 |
|---|---|---|
| **약 888만 행의 심박수 observation fact를 매일 생성할 것인가** | observation-level 분석 가능성 대 일상 build 비용 | 실제 소비자가 없다면 정규 build에서 제외하고 필요할 때 생성 |
| **원시 wearable fact를 Superset에 노출할 것인가** | Planning Team의 자유도 대 대형 ad-hoc query 위험 | 일별 `fct_wearable_day`만 일반 사용자에게 노출하고 원시 fact는 분석가 전용 |
| **endpoint 분리 트리거 승인** | Azure runbook을 실제로 시작할 기준 | §1.4의 70%/80%/90일 기준을 Azure 담당자와 합의 |
| **미사용 landing 데이터 보존 목적** | 저장공간보다 더 중요한 PII·유전체·임상 데이터 보유 책임 | 아래 R-5/R-6/R-7을 table 단위로 결정 |

### 5.2 기존 분석 정의 결정

**웨어러블 보유 정의:** step alone이 현재 wearable union 전체를 결정한다.
모든 stream 보유자가 step을 가지며, 44명의 cohort 사용자는 step만 있다.
휴대폰도 걸음 수를 생성할 수 있고 source에는 watch와 phone을 구분할 값이
없다.

- step 포함: 2026-07-31 기준 181명
- step 제외: 같은 기준 137명

“device 보유”라고 부르려면 휴대폰 pedometer도 device로 인정한다는 명시적
결정이 필요하다. 결정 전에는 `wearable_data_observed`처럼 관측 사실만
표현하는 명칭을 쓴다. wearable 수치는 retroactive backfill로 바뀌므로 항상
**cutoff와 extraction date를 함께 인용**한다.

### 5.3 데이터 최소화 및 보존 범위

dbt가 직접 읽는 landing relation은 27개, 직접 읽지 않는 relation은 98개이며
후자가 약 3.33GB를 차지한다. 크기만 보고 일괄 삭제하지 않는다. 미래 분석
가치와 민감정보 보존 책임을 table별로 판단한다.

- **R-5:** marts가 사용하지 않는 `ichms.auth_*` / `mem_*` table을 계속
  landing할지 결정한다. 직접 식별자 column cleanup은 완료됐다.
- **R-6:** marts가 사용하지 않는 `irs.job_input_data`의 genotype 및 기타
  payload를 DW에 보존할지 결정한다.
- **R-7:** Discovery consultation, examination, medical, prescription payload
  table이 필요한지 확인하고, 목적이 없으면 extraction target에서 제거한다.
- **R-8:** target config 변경과 loader의 upstream column 자동 추가 시 PII
  inventory를 다시 실행하는 절차를 runbook에 넣는다.
- `stg_sibc.daily_routine_activities`의 약 702MB TOAST는 dbt가 선택하지 않는
  raw JSONB 네 개가 대부분이다. 응답 원문 분석 계획이 없다면 제외 후보지만,
  기존 “landing은 source의 transient copy” 정책을 바꾸므로 owner 결정 없이
  삭제하지 않는다.
- `stg_iccoli.tb_action_user_log.target_data`도 현재 metric에는 쓰이지 않지만
  향후 action 분석 가능성이 있으므로 별도 보존 판단이 필요하다.

### 5.4 운영·접근 권한

- **Q-04 영구 담당자:** 현재 창민님이 임시 담당. 인수인계 시작, 담당자 변경,
  데이터 조직 개편 중 먼저 오는 시점에 다시 결정한다.
- **Planning Team:** dashboards-only 역할(Gamma에서 SQL Lab 제거)을 만든다.
- **AI client:** marts-only DB role만 허용한다. agent가 Superset Admin 세션을
  가질 수 있는지는 별도 결정한다.
- `SUPERSET_SECRET_KEY`, `superset_reader` 비밀번호와 app DB 비밀번호를
  로컬 `.env`에서 Key Vault 또는 비밀번호 관리자로 옮긴다.
- Superset app DB의 실제 backup/restore drill을 수행한다.

---

## 6. 외부 의존으로 막힌 항목

| 항목 | 필요한 상대와 조건 |
|---|---|
| endpoint migration runbook | Azure 담당자. connection 변경, dump/restore 또는 EL replay, role/grant, 검증, cutover, rollback 포함 |
| Azure storage 경고 | Azure 담당자. 70% 경고, 80% build 차단에 사용할 Monitor 접근 및 알림 채널 |
| dbt role `temp_file_limit` | Azure 관리자 권한과 정상 build peak 측정 필요 |
| 과거 site attribution | 개발팀의 unlink→insert 규칙, 수동 production DML 통지, 과거 13개 flip 복구 여부 필요 |
| 혈당 단위 | Discovery source가 행별 unit을 제공하면 현재 threshold heuristic 제거 가능 |
| unmapped cohort users 2명 | source owner가 실제 계정 상태와 mapping 누락 원인을 확인해야 함 |

현재 site reporting은 `dim_user.site_id`의 **현재값 필터**만 허용한다. 과거
event를 현재 site로 grouping하면 이동 전 기록까지 새 site로 재귀속된다.
historical/as-of site metric이나 temporal bridge는 source contract가 생기기
전까지 만들지 않는다.

---

## 7. 계속 유지할 설계 프레임

### Frame 1 — mart가 산출물이고 viewer는 교체 가능한 얇은 층이다

이 프로젝트의 분석 수준은 Spearman 상관, Mann-Whitney U, 공변량을 통제한
OLS까지 포함한다. Superset, Lightdash, Grafana 같은 GUI가 이 분석을 대신하지
않는다. 따라서 분석 깊이는 warehouse가 제공해야 하며 semantic layer는
PostgreSQL과 git에 남는다.

viewer를 바꾸더라도 mart와 metric definition은 유지돼야 한다.

### Frame 2 — 개별 요청이 아니라 반복되는 분석 연산을 위해 설계한다

| 분석 연산 | mart가 제공해야 할 것 |
|---|---|
| 상대시간 cohorting(M0–M7) | `months_since_joined` |
| 분모 명시 | numerator와 denominator의 paired columns |
| app 접근일 통제 | `app_login_events` |
| negative control | 동일 grain의 병렬 channel |
| 개인 내 변화 | history가 있는 user × period panel |
| segment moderation | conformed age, sex, BMI band |
| 관측 가능성 | channel별 `is_observable_*` |

이 일곱 연산을 지원하면 다음 요청은 새 프로젝트가 아니라 새 쿼리가 된다.

### Frame 3 — zero day가 분모다

행동 비율에는 아무것도 하지 않은 날이 필요하다. active day만 모은 spine은
분모를 줄여 모든 비율을 부풀린다. 그래서 `fct_user_day`는 관측 frontier까지
매일 한 행을 갖는 dense panel이다.

- upper bound는 `current_date`가 아니라 마지막 관측일이다.
- source가 아직 들어오지 않은 날짜를 zero로 만들지 않는다.
- enrolment 이전 실제 activity가 있으면 spine도 그 activity까지 시작한다.
- `assert_user_day_spine_loses_no_activity` reconciliation test는 삭제하지 않는다.

### Frame 4 — viewer는 Superset으로 결정됐다

Superset 선택은 분석 깊이가 아니라 content-as-code, marts-only DB role,
row-level security와 교체 가능성을 기준으로 했다. viewer 재검토 조건은
다음뿐이다.

- wide dataset과 한국어 UI를 제공해도 Planning Team이 self-service에 실패
- 임상·유전체 데이터에 대한 더 강한 audit logging 요구 발생

재검토 후보의 최소 acceptance test는 SQL 없이 한국어 UI에서
`fct_user_disease_day`를 `dim_disease.phenotype_kor`와 `dim_user.sex`로
filter할 수 있는지다.

---

## 8. 완료 이력 — 다시 할 필요 없는 작업

### 2026-08-13

- `fct_wearable_day`에 step, sleep hours, SpO2, heart-rate 일별 intensity를
  추가했다. sparse fact이므로 NULL은 stream 미관측이지 0이 아니다.
- 여섯 개 source-grain wearable fact를 추가했다:
  `fct_wearable_step`, `fct_wearable_activity`,
  `fct_wearable_heartrate`, `fct_wearable_oxygen_saturation`,
  `fct_wearable_sleep`, `fct_wearable_sleep_stage`.
- exact duplicate payload만 접고 multiplicity는 `source_row_count`에 보존했다.
- 2026-08-13 14:51 KST extraction 기준 distinct observation은 step 19,080,
  activity 14,061, heart-rate 8,877,550, SpO2 60,867, sleep session 10,314,
  sleep stage 614,708이었다. 이 수치는 extraction date 없이 상수처럼 인용하지
  않는다.
- `dim_user`에 weight, height, BMI, BMI band, owner-maintained staff/participant
  `cohort_group`, channel별 observability flag를 추가했다.
- `fct_user_day_wide`에 Superset용 segment column을 추가했다.
- 현재 site mapping을 구현했다. 416명 모두 하나의 active approved site를
  가지며 당시 Ulsan 392명, Jeju 24명이었다. history는 구현하지 않았다.
- 마지막 전체 `dbt build` 388/388이 통과했다.

### 2026-08-11

- Superset 6.1.0과 PostgreSQL app DB를 로컬에 배포했다.
- `superset_reader`를 marts-only, read-only, KST role로 만들고 실제 접속으로
  검증했다.
- 19개 marts relation과 PI dashboard 8개 chart를 script로 등록했다.
- `HOWTO.md`를 DB role, dataset 등록, one-chart-one-dataset 원칙 중심으로
  재작성했다.

### 2026-08-10 — wearable retroactive backfill

wearable은 measurement time으로 watermarking하지만 device가 수일 또는 수주
늦게 sync한다. source에는 insert timestamp가 없어 단순 watermark는 과거에
도착한 행을 영구적으로 놓쳤다.

- step에서 최대 29일 backfill을 측정해 30일 lookback을 정했다.
- step/activity/sleep/SpO2에 먼저 적용했고 8월 13일 heart-rate에도 적용했다.
- keyless table은 같은 widened window를 delete 후 insert하므로 replay가
  idempotent하다.
- child lifelog table만 갱신하고 `disc_lifelog_user_info` parent를 갱신하지
  않으면 row count가 늘면서 attributed user count가 줄 수 있다. 전체 system
  run이 안전하며, child를 수동 실행하면 parent도 바로 갱신한다.

### 2026-08-07 — dense behavioural panel

- `fct_user_day`를 5,747개 active day에서 74,410개 dense user-day로 바꿨다.
- 이후 backfill로 2026-08-10 기준 76,026행이 됐다.
- `days_since_joined`, `months_since_joined`, login, routine denominator pair,
  manual measurement, meal, wearable, app action, passive/active flag를 추가했다.
- 첫 spine이 381개 meal record와 23명의 recorder를 조용히 잃는 문제를
  reconciliation test가 발견했다. 이 때문에 grain/not-null test만으로는
  충분하지 않다.

---

## 9. 알려진 보류 사항

- **hard delete 전파:** watermark extraction은 source에서 삭제된 행을 보지
  못한다. table을 append-only와 mutable-without-marker로 분류하고 사용자 삭제
  요청 시 `stg_*`와 marts에서 user key로 제거하는 절차가 필요하다.
- **사용되지 않는 `generate_user_key()`:** 직접 식별자는 EL boundary에서
  제외하는 방식으로 해결했다. helper를 실제 정책에 연결하거나 삭제해야 한다.
- **byte 기준 batched loading:** 현재는 필요 없지만, 필요 시 row 수가 아니라
  byte budget별 watermark window로 `extract → load → commit`을 반복한다.
- **Discovery 대형 table의 watermark index:** heart-rate `measured_dt`에 단독
  usable index가 없어 30일 incremental extraction도 source를 seq-scan한다.
  production source DB 변경이므로 현재는 측정·모니터링만 한다.
- **PK 없는 incremental target:** loader의 delete-window-then-insert 전략으로
  idempotency를 유지한다. `KNOWN_MISSING_PRIMARY_KEY` test가 목록을 고정한다.
- **linter/CI 없음.**
- **Airflow `~=3.2.2` pin:** 배포 image와 함께 올린다.

---

## 10. 로컬 운영 상태

- Superset은 Colima VM의 `:8088`에서 실행되도록 구성돼 있다.
- admin, app DB, `SUPERSET_SECRET_KEY`, `superset_reader` 비밀번호는
  gitignore된 `deploy/superset/.env`에만 있다. durable secret store로 옮겨야
  한다.
- UI에서만 만든 추가 content나 별도 사용자가 없다면 Superset app DB는
  아직 git script로 대부분 재현 가능하다. backup/restore drill을 하기에 가장
  싼 시점이다.
- `register_marts_datasets.sh`는 marts의 모든 table/view를 등록하므로 대형 원시
  fact를 일반 사용자에게 노출할지 결정하기 전에는 무조건 재실행하지 않는다.
