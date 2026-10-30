#!/usr/bin/env bash
set -euo pipefail
if ! command -v python3 >/dev/null 2>&1; then
  printf 'Python 3.9+ required; install Python using your distribution package manager.\n' >&2
  exit 1
fi
python3 - <<'PY'
import sys
if sys.version_info < (3,9):
    sys.exit('Python 3.9+ required')
PY
src="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bindir="${HOME}/.local/bin"
mkdir -p -- "$bindir"
if [[ -e "$bindir/nbai" || -L "$bindir/nbai" ]]; then
  if [[ "$(readlink -f -- "$bindir/nbai")" != "$src/nbai.py" ]]; then
    printf 'Refusing to overwrite existing %s/nbai. Remove it manually after inspection.\n' "$bindir" >&2
    exit 1
  fi
else
  ln -s -- "$src/nbai.py" "$bindir/nbai"
fi
chmod +x -- "$src/nbai.py"
printf '\nInstalled CLI symlink: %s/nbai -> %s/nbai.py\n' "$bindir" "$src"
printf 'Ollama, its service, models and your existing MCP servers were not changed.\n'
printf 'Try: %s/nbai doctor\n' "$bindir"
