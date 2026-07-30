"""
Minimal test runner, so the suite works with or without pytest.

	uv run python tests/run_tests.py                  # everything
	uv run python tests/run_tests.py -k merge         # only matching names
	uv run python tests/run_tests.py --offline        # skip the database tests
	uv run python tests/run_tests.py -v               # show tracebacks

Once pytest is added to the project, `uv run pytest` discovers exactly the same
test functions -- they take no fixtures, and database access is a context manager
(`tests.db.sessions`) rather than an injected argument.
"""

import argparse
import importlib
import inspect
import pkgutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

from tests import db  # noqa: E402  (needs the path set up first)
from tests.db import Skipped  # noqa: E402

PACKAGES = ("tests", "tests.extract", "tests.load", "tests.transform")


def discover(name_filter: str | None):
	for package_name in PACKAGES:
		try:
			package = importlib.import_module(package_name)
		except ModuleNotFoundError:
			continue
		for module_info in pkgutil.iter_modules(package.__path__):
			if not module_info.name.startswith("test_"):
				continue
			module = importlib.import_module(f"{package_name}.{module_info.name}")
			for test_name, function in sorted(vars(module).items()):
				if not test_name.startswith("test_") or not inspect.isfunction(function):
					continue
				if function.__module__ != module.__name__:
					continue  # imported helper, not a test defined here
				if name_filter and name_filter not in f"{module.__name__}.{test_name}":
					continue
				yield module.__name__, test_name, function


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("-k", dest="name_filter", help="only run tests whose name contains this")
	parser.add_argument("--offline", action="store_true", help="skip every test that needs a database")
	parser.add_argument("-v", "--verbose", action="store_true", help="print tracebacks for failures")
	args = parser.parse_args()

	if args.offline:
		# Every database test funnels through tests.db, so one flag skips them all.
		db.OFFLINE = True

	passed = failed = skipped = 0
	failures: list[tuple[str, str]] = []
	current_module = None

	for module_name, test_name, function in discover(args.name_filter):
		if module_name != current_module:
			current_module = module_name
			print(f"\n{module_name}")
		try:
			function()
		except Skipped as exc:
			skipped += 1
			print(f"  SKIP {test_name}  ({exc})")
		except BaseException:
			failed += 1
			failures.append((f"{module_name}.{test_name}", traceback.format_exc()))
			print(f"  FAIL {test_name}")
		else:
			passed += 1
			print(f"  ok   {test_name}")

	if failures and args.verbose:
		for name, trace in failures:
			print(f"\n{'=' * 70}\nFAIL {name}\n{'=' * 70}\n{trace}")
	elif failures:
		print("\nRe-run with -v to see tracebacks.")

	print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
	return 1 if failed else 0


if __name__ == "__main__":
	sys.exit(main())
