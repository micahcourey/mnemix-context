#!/usr/bin/env python3
"""Bootstrap a rendered workspace for eval testing.

Runs generate.py with the reference config to produce a complete .ai/ directory,
then copies eval metadata into it so agents can be tested against rendered skills.

Usage:
    python3 evals/bootstrap_workspace.py [--output /path/to/workspace]
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EVALS_DIR = Path(__file__).parent
REPO_ROOT = EVALS_DIR.parent
REFERENCE_CONFIG = EVALS_DIR / "reference-config.yaml"


def bootstrap(output_dir: Path | None = None) -> Path:
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="eval-workspace-"))

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Run generate.py with reference config
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "setup" / "generate.py"),
            "--config", str(REFERENCE_CONFIG),
            "--output", str(output_dir),
        ],
        check=True,
    )

    # 2. Copy eval metadata into the rendered workspace
    eval_output = output_dir / ".ai" / "evals"
    eval_output.mkdir(parents=True, exist_ok=True)

    for skill_dir in EVALS_DIR.iterdir():
        if skill_dir.is_dir() and (skill_dir / "eval_metadata.json").exists():
            dest = eval_output / skill_dir.name
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                skill_dir / "eval_metadata.json",
                dest / "eval_metadata.json",
            )

    # 3. Copy runner + grader into workspace for agent access
    for script in ("run_eval.py", "grade_eval.py"):
        src = EVALS_DIR / script
        if src.exists():
            shutil.copy2(src, eval_output / script)

    print(f"Eval workspace bootstrapped at: {output_dir}")
    print(f"Rendered .ai/ with {len(list((output_dir / '.ai').rglob('*')))} files")
    return output_dir


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Bootstrap eval workspace")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output directory (default: temp directory)")
    args = parser.parse_args()
    bootstrap(args.output)
