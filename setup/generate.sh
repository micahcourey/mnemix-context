#!/usr/bin/env bash
# ============================================================================
# Mnemix Context - Generate Script
# ============================================================================
# Wrapper for setup/generate.py that handles Python environment detection.
#
# Usage:
#   ./setup/generate.sh                        # Generate from toolkit.config.yaml
#   ./setup/generate.sh --dry-run              # Preview without writing
#   ./setup/generate.sh --validate             # Validate config only
#   ./setup/generate.sh --config my.yaml       # Use custom config
#   ./setup/generate.sh --target copilot,cursor # Only these platforms
#   ./setup/generate.sh --target all           # All platforms
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Find Python 3
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1 | grep -o '3\.[0-9]*')
        if [[ -n "$version" ]]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    echo "❌ Python 3 is required but not found."
    echo "   Install: brew install python3 (macOS) or apt install python3 (Linux)"
    exit 1
fi

# Check for PyYAML
if ! "$PYTHON" -c "import yaml" 2>/dev/null; then
    echo "📦 Installing PyYAML..."
    "$PYTHON" -m pip install --quiet pyyaml
fi

# Run generator
cd "$ROOT_DIR"
exec "$PYTHON" setup/generate.py "$@"
