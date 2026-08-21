#!/usr/bin/env python3
"""Build the PI dashboard in Superset from the v_pi_* / v_bridge_* datasets.

This script recreates the legacy dashboard reviewed in METRICS.md as code:
charts, layout, and the
interpretation rules are all created through the REST API, so the
dashboard is reproducible from the repo instead of living only in an
admin's clicks.

Idempotent: charts are matched by name and updated in place; the dashboard
is matched by slug and its layout rewritten. Manual chart edits in the UI
survive only until the next run — by design, same reasoning as "metrics
live in git, not in dashboard cards".

Run from deploy/superset/ with the stack healthy:

	./scripts/build_pi_dashboard.py

Stdlib only, on purpose: this must run on the host with nothing installed.
"""

import json
import os
import sys
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import quote

BASE = None  # set in main() from .env
DASHBOARD_SLUG = "pi-metrics"
DASHBOARD_TITLE = "PI 지표 대시보드"

# The dashboard carries its legacy reading instructions (METRICS.md).
# A number nobody knows how to read is worse than no number.
NOTES_MARKDOWN = """\
### 해석 규칙 (METRICS.md)

1. **커버리지를 먼저 보세요.** 점수 받은 사람이 줄어든 달에 평균 위험도가 내려갔다면, \
위험이 줄어든 게 아니라 아픈 사람이 측정을 안 한 것일 수 있습니다.
2. **IRS/IRS+ 는 1~100 백분위 순위**입니다. 절대 위험도가 아니고, 더하거나 뺄 수 없습니다. 추세만 의미 있습니다.
3. 순응도 분모는 전달된 **모든** 활동입니다 (철회 포함). 활성 사용자는 **사람 수**입니다 — 한 명이 많이 눌러도 안 오릅니다.
4. KPI 뷰는 아직 없습니다 — 무엇이 왜 없는지는 아래 **브리지 등록부**가 데이터로 기록합니다.
"""


def _simple_metric(column, aggregate, label):
	return {
		"expressionType": "SIMPLE",
		"column": {"column_name": column},
		"aggregate": aggregate,
		"label": label,
		"optionName": f"metric_{column}_{aggregate.lower()}",
	}


def _line(dataset, x, metric, y_fmt="SMART_NUMBER", y_bounds=None):
	return {
		"viz_type": "echarts_timeseries_line",
		"x_axis": x,
		"time_grain_sqla": None,
		"metrics": [metric],
		"row_limit": 10000,
		"show_legend": False,
		"rich_tooltip": True,
		"x_axis_time_format": "smart_date",
		"y_axis_format": y_fmt,
		"y_axis_bounds": y_bounds or [None, None],
		"markerEnabled": False,
	}


def _bar(dataset, x, metric, y_fmt="SMART_NUMBER"):
	return {
		"viz_type": "echarts_timeseries_bar",
		"x_axis": x,
		"time_grain_sqla": None,
		"metrics": [metric],
		"row_limit": 100,
		"show_legend": False,
		"y_axis_format": y_fmt,
	}


# (chart name, dataset, form_data builder). One view = one metric = one chart;
# every timeseries is single-series, so no legends anywhere (dataviz rule).
CHARTS = [
	("일별 활성 사용자", "v_pi_app_engagement_daily",
		lambda: _line(None, "action_date", _simple_metric("active_users", "SUM", "활성 사용자"))),
	("주별 측정 참여자", "v_pi_measurement_participation_weekly",
		lambda: _bar(None, "week_start_date", _simple_metric("measuring_users", "SUM", "측정 참여자"))),
	("일별 코칭 순응도 (%)", "v_pi_coaching_adherence_daily",
		lambda: _line(None, "ymd_date", _simple_metric("adherence_pct", "AVG", "순응도 %"),
			y_fmt=",.1f", y_bounds=[0, 100])),
	("도메인별 코칭 순응도 (%)", "v_pi_coaching_adherence_by_domain",
		lambda: _bar(None, "domain", _simple_metric("adherence_pct", "AVG", "순응도 %"), y_fmt=",.1f")),
	("월별 스코어링 커버리지 (%) — 위험도보다 먼저 볼 것", "v_pi_scoring_coverage_monthly",
		lambda: _line(None, "month_start_date", _simple_metric("coverage_pct", "AVG", "커버리지 %"),
			y_fmt=",.1f", y_bounds=[0, 100])),
	("월별 평균 IRS+ (백분위 — 추세만)", "v_pi_population_risk_monthly",
		lambda: _line(None, "month_start_date", _simple_metric("mean_irs_plus", "AVG", "평균 IRS+"),
			y_fmt=",.1f")),
	("사용자당 고위험 질환 수 (월별)", "v_pi_high_risk_disease_load_monthly",
		lambda: _line(None, "month_start_date",
			_simple_metric("avg_high_risk_diseases", "AVG", "평균 고위험 질환 수"), y_fmt=",.2f")),
	("PI ↔ KPI 브리지 등록부 (무엇을 못 재고 있는가)", "v_bridge_pi_to_kpi",
		lambda: {
			"viz_type": "table",
			"query_mode": "raw",
			"all_columns": ["kpi_name_kor", "kpi_status", "pi_view",
				"interpretation_caveat", "data_required", "bridge_status"],
			"row_limit": 100,
		}),
]

# 12-column grid. Row heights are in Superset grid units (~8px).
LAYOUT = [  # rows of (chart_name, width)
	[("일별 활성 사용자", 6), ("주별 측정 참여자", 6)],
	[("일별 코칭 순응도 (%)", 6), ("도메인별 코칭 순응도 (%)", 6)],
	[("월별 스코어링 커버리지 (%) — 위험도보다 먼저 볼 것", 4),
	 ("월별 평균 IRS+ (백분위 — 추세만)", 4),
	 ("사용자당 고위험 질환 수 (월별)", 4)],
	[("PI ↔ KPI 브리지 등록부 (무엇을 못 재고 있는가)", 12)],
]
CHART_HEIGHT = 50


class Api:
	def __init__(self, base, username, password):
		self.base = base
		jar = CookieJar()
		self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
		tok = self._req("POST", "/api/v1/security/login", auth=False, body={
			"username": username, "password": password, "provider": "db", "refresh": False,
		})["access_token"]
		self.headers = {"Authorization": f"Bearer {tok}"}
		self.headers["X-CSRFToken"] = self._req("GET", "/api/v1/security/csrf_token/")["result"]

	def _req(self, method, path, body=None, auth=True):
		req = urllib.request.Request(self.base + path, method=method)
		for k, v in (self.headers.items() if auth else []):
			req.add_header(k, v)
		data = None
		if body is not None:
			req.add_header("Content-Type", "application/json")
			data = json.dumps(body).encode()
		with self.opener.open(req, data) as r:
			return json.loads(r.read() or "{}")

	def get_all(self, resource):
		out, page = [], 0
		while True:
			q = quote(f"(page:{page},page_size:100)")
			d = self._req("GET", f"/api/v1/{resource}/?q={q}")
			out.extend(d["result"])
			if len(out) >= d["count"] or not d["result"]:
				return out
			page += 1


def main():
	env = Path(__file__).resolve().parent.parent / ".env"
	cfg = dict(line.split("=", 1) for line in env.read_text().splitlines() if "=" in line)
	api = Api(f"http://localhost:{cfg.get('SS_HOST_PORT', '8088')}",
		cfg["SS_ADMIN_USER"], cfg["SS_ADMIN_PASSWORD"])

	datasets = {
		d["table_name"]: d["id"]
		for d in api.get_all("dataset")
		if d.get("schema") == "marts"
	}
	existing_charts = {c["slice_name"]: c["id"] for c in api.get_all("chart")}
	dashboards = {d["slug"]: d["id"] for d in api.get_all("dashboard") if d.get("slug")}

	dash_id = dashboards.get(DASHBOARD_SLUG)
	if dash_id is None:
		dash_id = api._req("POST", "/api/v1/dashboard/", body={
			"dashboard_title": DASHBOARD_TITLE, "slug": DASHBOARD_SLUG, "published": True,
		})["id"]
		print(f"created dashboard {DASHBOARD_SLUG} (id {dash_id})")
	else:
		print(f"dashboard {DASHBOARD_SLUG} exists (id {dash_id})")

	chart_ids = {}
	for name, table, form in CHARTS:
		ds = datasets.get(table)
		if ds is None:
			sys.exit(f"dataset marts.{table} not registered — run register_marts_datasets.sh first")
		fd = form()
		fd["datasource"] = f"{ds}__table"
		body = {
			"slice_name": name,
			"datasource_id": ds,
			"datasource_type": "table",
			"viz_type": fd["viz_type"],
			"params": json.dumps(fd, ensure_ascii=False),
			"dashboards": [dash_id],
		}
		if name in existing_charts:
			chart_ids[name] = existing_charts[name]
			api._req("PUT", f"/api/v1/chart/{chart_ids[name]}", body=body)
			print(f"updated  {name}")
		else:
			chart_ids[name] = api._req("POST", "/api/v1/chart/", body=body)["id"]
			print(f"created  {name}")

	# Layout: HEADER + markdown notes row + LAYOUT rows.
	# Keep direct references to the mutable `children` lists — indexing back
	# through `pos` loses the list type once the dict holds mixed values.
	pos = {
		"DASHBOARD_VERSION_KEY": "v2",
		"ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
		"HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": DASHBOARD_TITLE}},
	}
	grid_children: list[str] = []
	pos["GRID_ID"] = {"type": "GRID", "id": "GRID_ID", "children": grid_children, "parents": ["ROOT_ID"]}
	grid_children.append("ROW-notes")
	pos["ROW-notes"] = {"type": "ROW", "id": "ROW-notes", "children": ["MARKDOWN-notes"],
		"parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}}
	pos["MARKDOWN-notes"] = {"type": "MARKDOWN", "id": "MARKDOWN-notes", "children": [],
		"parents": ["ROOT_ID", "GRID_ID", "ROW-notes"],
		"meta": {"width": 12, "height": 26, "code": NOTES_MARKDOWN}}

	for i, row in enumerate(LAYOUT):
		row_id = f"ROW-{i}"
		grid_children.append(row_id)
		row_children: list[str] = []
		pos[row_id] = {"type": "ROW", "id": row_id, "children": row_children,
			"parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}}
		for name, width in row:
			cid = f"CHART-{chart_ids[name]}"
			row_children.append(cid)
			pos[cid] = {"type": "CHART", "id": cid, "children": [],
				"parents": ["ROOT_ID", "GRID_ID", row_id],
				"meta": {"chartId": chart_ids[name], "sliceName": name,
					"width": width, "height": CHART_HEIGHT}}

	api._req("PUT", f"/api/v1/dashboard/{dash_id}", body={
		"position_json": json.dumps(pos, ensure_ascii=False),
		"json_metadata": json.dumps({"color_scheme": "supersetColors", "refresh_frequency": 0}),
		"published": True,
	})
	print(f"layout written — http://localhost:{cfg.get('SS_HOST_PORT', '8088')}"
		f"/superset/dashboard/{DASHBOARD_SLUG}/")


if __name__ == "__main__":
	main()
