#!/usr/bin/env bash
set -euo pipefail
src="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
link="${HOME}/.local/bin/nbai"
if [[ -L "$link" && "$(readlink -f -- "$link")" == "$src/nbai.py" ]]; then
  rm -- "$link"
  printf 'Removed nbai launcher. Ollama and its user service are unchanged.\n'
else
  printf 'No matching nbai launcher found; not removing anything.\n'
fi
printf 'If installed, remove only the nightbreed-local-ai MCP entry from ~/.gemini/config/mcp_config.json yourself.\n'
printf 'Your optional private search index remains at ~/.local/share/nbai/index.sqlite3 until you remove it.\n'
