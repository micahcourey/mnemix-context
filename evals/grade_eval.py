#!/usr/bin/env python3
"""Grade eval results using deterministic checks and optional LLM judging.

Usage:
    python3 evals/grade_eval.py <skill-name>/iteration-<N>
    python3 evals/grade_eval.py --check-threshold 0.9 <skill-name>/iteration-<N>
"""

import argparse
import json
import re
import sys
from pathlib import Path


EVALS_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Deterministic assertion checkers
# ---------------------------------------------------------------------------

def check_transcript_contains(transcript: str, pattern: str) -> tuple[bool, str]:
    """Check if transcript contains pattern (regex)."""
    match = re.search(pattern, transcript, re.IGNORECASE)
    if match:
        start = max(0, match.start() - 50)
        end = min(len(transcript), match.end() + 50)
        return True, f"Found: ...{transcript[start:end]}..."
    return False, f"Pattern '{pattern}' not found in transcript"


def check_transcript_not_contains(transcript: str, pattern: str) -> tuple[bool, str]:
    """Check that transcript does NOT contain pattern."""
    passed, evidence = check_transcript_contains(transcript, pattern)
    if not passed:
        return True, f"Correctly absent: pattern '{pattern}' not in transcript"
    return False, f"Unexpectedly found: {evidence}"


def check_transcript_order(transcript: str, first: str, second: str) -> tuple[bool, str]:
    """Check that 'first' appears before 'second' in transcript."""
    m1 = re.search(first, transcript, re.IGNORECASE)
    m2 = re.search(second, transcript, re.IGNORECASE)
    if not m1:
        return False, f"First pattern '{first}' not found"
    if not m2:
        return False, f"Second pattern '{second}' not found"
    if m1.start() < m2.start():
        return True, f"'{first}' at pos {m1.start()} before '{second}' at pos {m2.start()}"
    return False, f"'{first}' at pos {m1.start()} AFTER '{second}' at pos {m2.start()}"


DETERMINISTIC_CHECKS = {
    "transcript_contains": lambda t, a: check_transcript_contains(t, a["pattern"]),
    "transcript_not_contains": lambda t, a: check_transcript_not_contains(t, a["pattern"]),
    "transcript_order": lambda t, a: check_transcript_order(t, a["first"], a["second"]),
}


# ---------------------------------------------------------------------------
# Grading engine
# ---------------------------------------------------------------------------

def grade_run(transcript: str, assertions: list) -> dict:
    """Grade a single run against its assertions."""
    results = []
    for assertion in assertions:
        if assertion["type"] == "deterministic":
            checker = DETERMINISTIC_CHECKS.get(assertion["check"])
            if checker:
                passed, evidence = checker(transcript, assertion)
                results.append({
                    "id": assertion.get("id", "unknown"),
                    "text": assertion["description"],
                    "passed": passed,
                    "evidence": evidence,
                })
            else:
                results.append({
                    "id": assertion.get("id", "unknown"),
                    "text": assertion["description"],
                    "passed": False,
                    "evidence": f"Unknown check type: {assertion['check']}",
                })
        elif assertion["type"] == "llm-judge":
            # Placeholder — LLM grading is Phase 2
            results.append({
                "id": assertion.get("id", "unknown"),
                "text": assertion["description"],
                "passed": None,  # null = not graded
                "evidence": "LLM judging not yet implemented — manual review required",
            })

    passed_count = sum(1 for r in results if r["passed"] is True)
    failed_count = sum(1 for r in results if r["passed"] is False)
    total = len(results)

    return {
        "assertion_results": results,
        "summary": {
            "passed": passed_count,
            "failed": failed_count,
            "ungraded": total - passed_count - failed_count,
            "total": total,
            "pass_rate": round(passed_count / total, 2) if total else 0,
        },
    }


def load_evals(skill_dir: Path) -> list:
    """Load test cases from both toolkit and user eval files."""
    evals = []
    for filename in ("eval_metadata.json", "custom_evals.json"):
        path = skill_dir / filename
        if path.exists():
            data = json.loads(path.read_text())
            evals.extend(data.get("evals", []))
    return evals


def grade_iteration(iteration_path: str) -> dict:
    """Grade all eval cases in an iteration directory."""
    # Parse path: <skill-name>/iteration-<N>
    parts = Path(iteration_path).parts
    if len(parts) < 2:
        sys.exit(f"Expected format: <skill-name>/iteration-<N>, got: {iteration_path}")

    skill_name = parts[0]
    iter_name = parts[1]

    skill_dir = EVALS_DIR / skill_name
    iter_dir = skill_dir / iter_name

    if not iter_dir.exists():
        sys.exit(f"Iteration directory not found: {iter_dir}")

    evals = load_evals(skill_dir)
    eval_map = {e["name"]: e for e in evals}

    benchmark = {"skill": skill_name, "iteration": iter_name, "cases": []}

    for case_dir in sorted(iter_dir.iterdir()):
        if not case_dir.is_dir() or not case_dir.name.startswith("eval-"):
            continue

        case_name = case_dir.name[len("eval-"):]
        case_meta = eval_map.get(case_name)
        if not case_meta:
            print(f"  ⚠️  No metadata for {case_name}, skipping")
            continue

        case_result = {"name": case_name, "with_skill": None, "without_skill": None}

        # Grade with_skill
        with_transcript = case_dir / "with_skill" / "transcript.md"
        if with_transcript.exists():
            transcript = with_transcript.read_text()
            grading = grade_run(transcript, case_meta.get("assertions", []))
            (case_dir / "with_skill" / "grading.json").write_text(
                json.dumps(grading, indent=2) + "\n"
            )
            case_result["with_skill"] = grading["summary"]

        # Grade without_skill (baseline)
        without_transcript = case_dir / "without_skill" / "transcript.md"
        if without_transcript.exists():
            transcript = without_transcript.read_text()
            grading = grade_run(transcript, case_meta.get("assertions", []))
            (case_dir / "without_skill" / "grading.json").write_text(
                json.dumps(grading, indent=2) + "\n"
            )
            case_result["without_skill"] = grading["summary"]

        benchmark["cases"].append(case_result)

    # Write aggregate benchmark
    with_pass_rates = [
        c["with_skill"]["pass_rate"]
        for c in benchmark["cases"]
        if c["with_skill"]
    ]
    benchmark["aggregate"] = {
        "avg_pass_rate": round(
            sum(with_pass_rates) / len(with_pass_rates), 2
        ) if with_pass_rates else 0,
        "cases_graded": len(with_pass_rates),
    }

    benchmark_path = iter_dir / "benchmark.json"
    benchmark_path.write_text(json.dumps(benchmark, indent=2) + "\n")
    print(f"Benchmark written to: {benchmark_path}")
    print(f"  Aggregate pass rate: {benchmark['aggregate']['avg_pass_rate']}")

    return benchmark


def main():
    parser = argparse.ArgumentParser(description="Grade eval results")
    parser.add_argument("iteration", help="Path like mnemix-memory/iteration-1")
    parser.add_argument("--check-threshold", type=float, default=None,
                        help="Fail with exit code 1 if pass rate below threshold")
    args = parser.parse_args()

    benchmark = grade_iteration(args.iteration)

    if args.check_threshold is not None:
        rate = benchmark["aggregate"]["avg_pass_rate"]
        if rate < args.check_threshold:
            print(f"❌ Pass rate {rate} below threshold {args.check_threshold}")
            sys.exit(1)
        else:
            print(f"✅ Pass rate {rate} meets threshold {args.check_threshold}")


if __name__ == "__main__":
    main()
