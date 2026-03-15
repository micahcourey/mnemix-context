#!/usr/bin/env python3
"""Run skill evals against an AI agent CLI.

Usage:
    # In core repo (mnemix-context):
    python3 evals/run_eval.py <skill-name> --platform codex --bootstrap

    # In end-user projects (already rendered):
    python3 .ai/evals/run_eval.py <skill-name> --platform codex [--iteration N]

The --bootstrap flag renders a workspace from templates before running evals.
This is how we test skills in the core repo before shipping them to end users.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from time import time


EVALS_DIR = Path(__file__).parent


def load_evals(skill_dir: Path) -> list:
    """Load test cases from both toolkit and user eval files."""
    evals = []
    for filename in ("eval_metadata.json", "custom_evals.json"):
        path = skill_dir / filename
        if path.exists():
            data = json.loads(path.read_text())
            evals.extend(data.get("evals", []))
    return evals


def bootstrap_workspace() -> Path:
    """Render a complete workspace from templates for eval testing."""
    bootstrap_script = EVALS_DIR / "bootstrap_workspace.py"
    if not bootstrap_script.exists():
        sys.exit("--bootstrap is only available in the mnemix-context core repo")

    import importlib.util
    spec = importlib.util.spec_from_file_location("bootstrap", bootstrap_script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.bootstrap()


def run_with_codex(prompt: str, cwd: Path) -> dict:
    """Run a prompt via codex exec and capture the JSONL trace."""
    cmd = ["codex", "exec", "--json", "--full-auto", prompt]
    start = time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=cwd)
    duration = time() - start
    return {
        "transcript": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.returncode,
        "duration_ms": int(duration * 1000),
    }


def run_with_claude(prompt: str, cwd: Path) -> dict:
    """Run a prompt via claude CLI and capture output."""
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    start = time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=cwd)
    duration = time() - start
    return {
        "transcript": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.returncode,
        "duration_ms": int(duration * 1000),
    }


RUNNERS = {
    "codex": run_with_codex,
    "claude": run_with_claude,
}


def run_eval(skill_name: str, platform: str, iteration: int, workspace: Path):
    """Run evals for a skill inside the given workspace directory."""
    skill_dir = EVALS_DIR / skill_name
    evals = load_evals(skill_dir)

    if not evals:
        sys.exit(f"No eval cases found for skill: {skill_name}")

    runner = RUNNERS.get(platform)
    if not runner:
        sys.exit(f"Unsupported platform: {platform}. Supported: {', '.join(RUNNERS)}")

    iter_dir = skill_dir / f"iteration-{iteration}"

    for case in evals:
        case_dir = iter_dir / f"eval-{case['name']}"

        # With skill — agent runs inside the rendered workspace (sees .ai/)
        with_dir = case_dir / "with_skill"
        with_dir.mkdir(parents=True, exist_ok=True)
        result = runner(case["prompt"], cwd=workspace)
        (with_dir / "transcript.md").write_text(result["transcript"])
        (with_dir / "timing.json").write_text(json.dumps({
            "duration_ms": result["duration_ms"],
        }, indent=2))

        # Without skill (baseline) — agent runs in a bare directory
        without_dir = case_dir / "without_skill"
        without_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="eval-baseline-") as bare:
            baseline = runner(case["prompt"], cwd=Path(bare))
        (without_dir / "transcript.md").write_text(baseline["transcript"])
        (without_dir / "timing.json").write_text(json.dumps({
            "duration_ms": baseline["duration_ms"],
        }, indent=2))

    print(f"Eval complete: {skill_name} iteration-{iteration}")
    print(f"Results at: {iter_dir}")


def main():
    parser = argparse.ArgumentParser(description="Run skill evals")
    parser.add_argument("skill", help="Skill name (e.g., mnemix-memory)")
    parser.add_argument("--platform", required=True, choices=list(RUNNERS),
                        help="AI platform CLI to use")
    parser.add_argument("--iteration", type=int, default=1,
                        help="Iteration number (default: 1)")
    parser.add_argument("--bootstrap", action="store_true",
                        help="Bootstrap workspace from templates first (core repo only)")
    args = parser.parse_args()

    if args.bootstrap:
        workspace = bootstrap_workspace()
    else:
        workspace = Path.cwd()

    run_eval(args.skill, args.platform, args.iteration, workspace)


if __name__ == "__main__":
    main()
