# analysis/

웨어하우스 데이터를 대상으로 한 일회성 분석 노트북. ELT 파이프라인(`src/`, `dags/`)과는 분리돼 있고,
`data/csv/` 의 CSV 만 읽는다 — 노트북이 DB 에 직접 붙지 않으므로 커널을 켠 채로 두어도 커넥션이 새지 않는다.

| 노트북 | 플롯 언어 | 내용 |
|---|---|---|
| `point_mission_liability.ipynb` | 영문 | 포인트 미션 × 30일 사용자 활동 상관분석 (부채 관점) |
| `point_mission_liability_ko.ipynb` | **한글 (D2Coding)** | 위와 내용 동일. 플롯 글자만 한글 |

두 노트북은 **셀 구성·계산·결론이 완전히 같고** 표현만 다르다. 외부 전달용은 `_ko` 쪽.

| | 영문판 | 한글판 (`_ko`) |
|---|---|---|
| 플롯 글자 | 영문 | 한글 (D2Coding) |
| 표 컬럼명 | 원본 컬럼명 | 한글 |
| 서술 문체 | ~이다 | ~입니다 |

표 컬럼명은 `show()` 헬퍼가 `COLS` 매핑으로 바꿔 출력한다. 영문판은 `COLS = {}` 라 원본이 그대로 나오고,
한글판만 매핑이 채워져 있다. 호출부는 양쪽이 동일하므로 계산 코드가 갈라지지 않는다.

## 공유용 엑셀

```bash
uv run python analysis/build_report_xlsx.py     # → data/포인트_미션_분석.xlsx
```

`data/csv/` 의 CSV 를 **미션(01) 기준으로** 합쳐 시트 6개짜리 워크북 하나로 만든다.
노트북과 함께 전달하는 것을 전제로 하며, `판단` 컬럼은 노트북 4·6절과 같은 계산을 쓴다.

| 시트 | 내용 |
|---|---|
| 0. 읽는 법 | 기준일·시트 안내·용어·합계가 시트마다 다른 이유 |
| 1. 부채 요약 | 발행/사용/잔액 전체 집계 |
| 2. 미션 종합 | **메인.** 미션 1행 — 카탈로그 + 부채 + 적립자 활동 + 효과 추정 + 판단 |
| 3. 포인트 부채 | 미션별 금액 상세 (삭제된 미션 포함, 합계가 맞는 쪽) |
| 4. 월별 발행 | 미션 × 월 피벗 |
| 5. 적립자 활동 | 미션별 적립자 집단의 30일 활동 프로필 |

**사용자 단위 CSV(02/03/04/08)는 넣지 않는다.** raw `user_no` / `user_id` 가 들어 있어
외부 공유 대상이 아니다. 워크북에는 미션 단위로 집계한 값만 담긴다.

## 실행

의존성은 `pyproject.toml` 의 `analysis` 그룹에 있고, `[tool.uv] default-groups` 에 등록해 뒀으므로
평범한 `uv sync` 로 함께 설치된다.

```bash
uv sync                                   # jupyter/pandas/matplotlib/scipy/statsmodels 포함
bash data/sql/build_all.sh                # 입력 CSV 재생성 (선행)
uv run jupyter lab                        # 대화형
uv run jupyter nbconvert --to notebook --execute --inplace \
    analysis/point_mission_liability_ko.ipynb   # 전체 재실행
```

노트북은 열린 위치(repo 루트 / `analysis/`)와 무관하게 `data/csv` 를 위로 거슬러 찾는다.

## 플롯 폰트

| | 폰트 설정 |
|---|---|
| 영문판 | `font.family = ["DejaVu Sans", "D2Coding"]` — D2Coding 은 폴백으로만 등록 |
| 한글판 | `font.family = ["D2Coding", "DejaVu Sans"]` — D2Coding 이 1순위. 없으면 첫 셀에서 명시적으로 실패 |

`~/Library/Fonts/D2Coding-Ver1.3.2-20180524.ttf` 를 `fontManager.addfont()` 로 등록해서 쓴다.
matplotlib 이 그림을 PNG 로 래스터화하므로 **PDF 로 변환해도 플롯 글자는 깨지지 않는다** — 폰트가
뷰어에 없어도 상관없다. 축·범례·제목·눈금 전부 확인했고 마이너스 기호(−), 가운뎃점(·), 물결(~) 모두 정상이다.

D2Coding 은 고정폭 폰트라 라벨이 다소 넓게 잡힌다. 비례폭을 원하면 첫 셀의 `font.family` 를
`["Apple SD Gothic Neo", ...]` 나 `["NanumGothic", ...]` 로 바꾸면 된다 (둘 다 이 머신에 설치돼 있음).

## PDF 로 내보내기

플롯은 위 이유로 안전하지만, **마크다운 서술의 한글**은 변환 경로를 탄다. 브라우저 경유가 가장 확실하다.

```bash
# 권장: HTML 로 뽑고 브라우저에서 "PDF로 저장"
uv run jupyter nbconvert --to html analysis/point_mission_liability_ko.ipynb

# 대안: headless Chromium 으로 바로 PDF (playwright 설치 필요)
uv run playwright install chromium
uv run jupyter nbconvert --to webpdf analysis/point_mission_liability_ko.ipynb
```

`--to pdf` (XeLaTeX 경로)는 한글 마크다운에서 폰트 설정이 따로 필요해 권장하지 않는다.

## 산출물 취급

노트북 출력에는 집계값만 들어간다 (`user_no` / `user_id` 원본은 표에 찍지 않는다 — 확인 완료).
`analysis/*.html`, `analysis/*.pdf` 는 `.gitignore` 에 있으니 필요할 때 다시 뽑아 쓰면 된다.
