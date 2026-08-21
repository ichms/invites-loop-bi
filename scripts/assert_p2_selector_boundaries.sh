#!/bin/bash
# Read-only graph contract for P2. Source setup_env.sh before running.
set -euo pipefail

PROJECT_DIR="${1:-dbt}"

daily_models=$(uv run dbt --quiet ls --project-dir "$PROJECT_DIR" \
	--selector daily_core --resource-type model --output name)
detail_models=$(uv run dbt --quiet ls --project-dir "$PROJECT_DIR" \
	--selector wearable_detail --resource-type model --output name)
daily_tests=$(uv run dbt --quiet ls --project-dir "$PROJECT_DIR" \
	--selector daily_core --resource-type test --output name)
detail_tests=$(uv run dbt --quiet ls --project-dir "$PROJECT_DIR" \
	--selector wearable_detail --resource-type test --output name)

detail_facts=(
	fct_wearable_activity
	fct_wearable_heartrate
	fct_wearable_oxygen_saturation
	fct_wearable_sleep
	fct_wearable_sleep_stage
	fct_wearable_step
)

for model_name in "${detail_facts[@]}"; do
	if rg --fixed-strings --line-regexp --quiet "$model_name" <<<"$daily_models"; then
		echo "daily_core unexpectedly selects $model_name" >&2
		exit 1
	fi
	if ! rg --fixed-strings --line-regexp --quiet "$model_name" <<<"$detail_models"; then
		echo "wearable_detail does not select $model_name" >&2
		exit 1
	fi
done

for test_name in \
	assert_wearable_observation_counts_reconcile \
	assert_wearable_observations_all_attributed
do
	if rg --fixed-strings --line-regexp --quiet "$test_name" <<<"$daily_tests"; then
		echo "daily_core unexpectedly selects $test_name" >&2
		exit 1
	fi
	if ! rg --fixed-strings --line-regexp --quiet "$test_name" <<<"$detail_tests"; then
		echo "wearable_detail does not select $test_name" >&2
		exit 1
	fi
done

if ! rg --fixed-strings --line-regexp --quiet fct_wearable_day <<<"$daily_models"; then
	echo "daily_core lost the sparse daily wearable fact" >&2
	exit 1
fi

echo "P2 selector boundary verified: daily_core excludes six detail facts and dedicated tests"
