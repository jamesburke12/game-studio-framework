#!/usr/bin/env python3
"""Compare NUnit3 test report against baseline to identify regressions."""

import sys
import json
import xml.etree.ElementTree as ET
import argparse
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def parse_nunit_report(xml_path):
    """Extract failing test full names from NUnit3 XML report."""
    if not Path(xml_path).exists():
        return []

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError:
        return []

    failures = []
    # NUnit3 format: test-case elements with result="Failed" or result="Error"
    for test_case in root.findall(".//test-case"):
        result = test_case.get("result", "").lower()
        if result in ("failed", "error"):
            full_name = test_case.get("fullname", "")
            if full_name:
                failures.append(full_name)

    return sorted(failures)


def load_baseline(baseline_path):
    """Load baseline JSON file mapping mode -> [failing test names]."""
    if not Path(baseline_path).exists():
        return {"EditMode": [], "PlayMode": []}

    try:
        with open(baseline_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"EditMode": [], "PlayMode": []}


def save_baseline(baseline_path, data):
    """Write baseline JSON file."""
    Path(baseline_path).parent.mkdir(parents=True, exist_ok=True)
    with open(baseline_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def compare_mode(current_failures, baseline_failures):
    """Compare current failures against baseline.

    Returns (regressions, preexisting, fixed) as lists of test names.
    """
    current_set = set(current_failures)
    baseline_set = set(baseline_failures)

    regressions = sorted(current_set - baseline_set)
    preexisting = sorted(current_set & baseline_set)
    fixed = sorted(baseline_set - current_set)

    return regressions, preexisting, fixed


def run_compare(report_path, baseline_path, mode, output_path):
    """Parse report, compare against baseline, write summary."""
    current_failures = parse_nunit_report(report_path)
    baseline_data = load_baseline(baseline_path)
    baseline_failures = baseline_data.get(mode, [])

    regressions, preexisting, fixed = compare_mode(current_failures, baseline_failures)

    summary = {
        "mode": mode,
        "total": len(current_failures),
        "failed": len(current_failures),
        "regressions": regressions,
        "preexisting": preexisting,
        "fixed": fixed
    }

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    # Print one-line summary
    print(f"{mode}: {len(regressions)} regressions, {len(preexisting)} pre-existing, {len(fixed)} fixed")

    return summary


def run_write_baseline(report_path, baseline_path, mode):
    """Parse report and merge its failures into the baseline."""
    current_failures = parse_nunit_report(report_path)
    baseline_data = load_baseline(baseline_path)

    baseline_data[mode] = sorted(set(baseline_data.get(mode, []) + current_failures))
    save_baseline(baseline_path, baseline_data)

    print(f"{mode}: recorded {len(baseline_data[mode])} known failures in baseline")


def run_selftest():
    """Self-test: create tiny NUnit XML, verify subtraction logic."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a minimal NUnit3 XML with 3 tests: 2 pass, 1 fails
        xml_path = tmpdir / "test.xml"
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
<test-run id="1" name="Test Run" fullname="Test Run" testcasecount="3" passed="2" failed="1">
  <test-suite id="2" name="TestNamespace.TestClass" fullname="TestNamespace.TestClass" type="TestFixture" testcasecount="3" passed="2" failed="1">
    <test-case id="3" name="TestA" fullname="TestNamespace.TestClass.TestA" result="Passed" />
    <test-case id="4" name="TestB" fullname="TestNamespace.TestClass.TestB" result="Passed" />
    <test-case id="5" name="TestC" fullname="TestNamespace.TestClass.TestC" result="Failed" />
  </test-suite>
</test-run>"""
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        # Test 1: parse XML
        failures = parse_nunit_report(str(xml_path))
        assert failures == ["TestNamespace.TestClass.TestC"], f"Parse failed: {failures}"

        # Test 2: write and load baseline
        baseline_path = tmpdir / "baseline.json"
        baseline_data = {"EditMode": [], "PlayMode": []}
        save_baseline(str(baseline_path), baseline_data)
        loaded = load_baseline(str(baseline_path))
        assert loaded == baseline_data, f"Baseline save/load failed: {loaded}"

        # Test 3: compare with no baseline
        regressions, preexisting, fixed = compare_mode(failures, [])
        assert regressions == ["TestNamespace.TestClass.TestC"], f"Regression detection failed: {regressions}"
        assert preexisting == [], f"Preexisting should be empty: {preexisting}"
        assert fixed == [], f"Fixed should be empty: {fixed}"

        # Test 4: compare with baseline containing one of the failures
        baseline_failures = ["TestNamespace.TestClass.TestC"]
        regressions, preexisting, fixed = compare_mode(failures, baseline_failures)
        assert regressions == [], f"Should have no regressions: {regressions}"
        assert preexisting == ["TestNamespace.TestClass.TestC"], f"Should be preexisting: {preexisting}"
        assert fixed == [], f"Fixed should be empty: {fixed}"

        # Test 5: compare with baseline containing an extra failure
        baseline_failures = ["TestNamespace.TestClass.TestC", "TestNamespace.TestClass.TestD"]
        regressions, preexisting, fixed = compare_mode(failures, baseline_failures)
        assert regressions == [], f"Should have no regressions: {regressions}"
        assert preexisting == ["TestNamespace.TestClass.TestC"], f"Should be preexisting: {preexisting}"
        assert fixed == ["TestNamespace.TestClass.TestD"], f"Should have fixed TestD: {fixed}"

        print("✓ All self-tests passed")
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Compare NUnit3 test report against baseline to identify regressions."
    )
    parser.add_argument("report", nargs="?", help="Path to NUnit3 XML report")
    parser.add_argument("--baseline", help="Path to baseline JSON file (input)")
    parser.add_argument("--mode", choices=["EditMode", "PlayMode"], help="Test mode (EditMode or PlayMode)")
    parser.add_argument("--out", help="Path to output summary JSON")
    parser.add_argument("--write-baseline", help="Path to baseline JSON file (output mode: merge this report into baseline)")
    parser.add_argument("--selftest", action="store_true", help="Run self-tests and exit")

    args = parser.parse_args()

    if args.selftest:
        success = run_selftest()
        sys.exit(0 if success else 1)

    if not args.report:
        parser.print_help()
        sys.exit(1)

    if args.write_baseline:
        if not args.mode:
            print("Error: --mode is required when using --write-baseline", file=sys.stderr)
            sys.exit(1)
        run_write_baseline(args.report, args.write_baseline, args.mode)
        sys.exit(0)

    if not args.baseline or not args.mode:
        print("Error: --baseline and --mode are required for comparison", file=sys.stderr)
        sys.exit(1)

    summary = run_compare(args.report, args.baseline, args.mode, args.out)

    # Exit 1 if there are regressions, else 0
    sys.exit(1 if summary["regressions"] else 0)


if __name__ == "__main__":
    main()
