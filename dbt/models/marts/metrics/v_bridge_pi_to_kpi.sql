-- BRIDGE REGISTER: what we measure vs. what the organisation is judged on.
--
-- The headline KPIs live in the business documents; none of them can be
-- computed from this warehouse, because it holds no admission, discharge,
-- claim or billing data. Rather than ship `v_kpi_*` views that return NULL —
-- rejected under Q-08, because a NULL KPI erodes trust in the real numbers and
-- someone eventually cites it anyway — the gap is written down as data.
--
-- This is a deliberately static VALUES list, not a query. It is a register: a
-- reviewable, diffable statement of which proxy stands in for which outcome and
-- what is missing. It belongs in SQL so the Planning Team can read it in
-- Metabase next to the metrics it qualifies, instead of in a document nobody
-- opens.
--
-- Maintenance: when a data source arrives, add the real `v_kpi_*` view and
-- update that row's status here. The register is the to-do list.

select *
from (
	values
		(
			'재입원율 (30일)',
			'30-day readmission rate',
			'없음 — 입퇴원 데이터가 웨어하우스에 존재하지 않음',
			'v_pi_coaching_adherence_daily',
			'행동 변화 순응도가 재입원 감소의 선행지표라는 가설. 인과관계는 검증되지 않음',
			'EMR 입퇴원 기록 (admission/discharge), 병원 시스템 연동 필요',
			'blocked'
		),
		(
			'재원일수 (LOS)',
			'Length of stay',
			'없음 — 병원 운영 데이터 미연동',
			NULL,
			'현재 대응하는 선행지표 없음',
			'EMR 입퇴원 기록',
			'blocked'
		),
		(
			'MSPB / 의료비 지출',
			'Medicare spending per beneficiary',
			'없음 — 청구 데이터 미연동',
			NULL,
			'현재 대응하는 선행지표 없음',
			'청구(claim) 데이터, 지불자 연동',
			'blocked'
		),
		(
			'원격관리 유지율',
			'Remote care retention',
			'없음 — 계약/청구 기준 정의 미확정',
			'v_pi_app_engagement_daily',
			'앱 활동 지속이 프로그램 잔존의 대리 지표. 이탈 정의가 확정되면 KPI로 승격 가능',
			'이탈(churn) 정의 합의 + 등록/해지 이벤트',
			'proxy_available'
		),
		(
			'임상 위험도 개선',
			'Clinical risk improvement',
			'없음 — 추적관찰 데이터 부재로 임상 검증 불가',
			'v_pi_population_risk_monthly',
			'IRS+ 는 백분위 순위이므로 추세만 해석 가능. 절대 위험도나 임상 결과로 읽으면 안 됨',
			'추적관찰(follow-up) 결과 데이터',
			'proxy_available'
		),
		(
			'디바이스 측정 순응도',
			'Device measurement adherence',
			'없음 — 디바이스 배포 기록이 어느 소스에도 없음',
			'v_pi_measurement_participation_weekly',
			'측정 제출 사용자 수는 관찰 가능하나, 분모(배포 대상자)를 알 수 없어 비율 계산 불가',
			'디바이스 배포/할당 기록 (dim_user 의 배포 플래그가 비어 있는 이유)',
			'partial'
		)
) as t (
	kpi_name_kor,
	kpi_name_eng,
	kpi_status,
	pi_view,
	interpretation_caveat,
	data_required,
	bridge_status
)
