#!/usr/bin/env python3
"""Initialize an external Mnemix store for this project."""

import argparse
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize an external Mnemix store")
    parser.add_argument("--binary", default="mnemix", help="Path to the mnemix CLI binary")
    parser.add_argument("--store-path", default=".mnemix", help="Path to the Mnemix store (default: .mnemix)")
    args = parser.parse_args()

    if shutil.which(args.binary) is None:
        print(f"Error: '{args.binary}' was not found on PATH.", file=sys.stderr)
        print("Install Mnemix first: pip install mnemix", file=sys.stderr)
        return 1

    subprocess.run([args.binary, "--store", args.store_path, "init"], check=True)

    print()
    print("Mnemix store initialized.")
    print(f"  Binary: {args.binary}")
    print(f"  Store:  {args.store_path}")
    print()
    print("Examples:")
    print(f"  {args.binary} --store {args.store_path} recall --scope repo:your-project")
    print(f"  {args.binary} --store {args.store_path} search --text \"decision\" --scope repo:your-project")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
