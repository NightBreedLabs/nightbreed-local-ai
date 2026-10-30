#!/usr/bin/env bash
# Create a new PUBLIC NightBreedLabs repository and push this vetted source tree.
set -euo pipefail

repo='NightBreedLabs/nightbreed-local-ai'
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

if ! command -v gh >/dev/null 2>&1; then
  printf '%s\n' 'GitHub CLI (gh) is required. On Linuxbrew: brew install gh' >&2
  exit 1
fi
if ! command -v git >/dev/null 2>&1; then
  printf '%s\n' 'Git is required.' >&2
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  printf '%s\n' 'Authenticate GitHub CLI first: gh auth login' >&2
  exit 1
fi
if gh repo view "$repo" >/dev/null 2>&1; then
  printf 'Repository %s already exists. Refusing to overwrite or push to an existing repository.\n' "$repo" >&2
  exit 1
fi
if [[ -d .git ]]; then
  if git remote get-url origin >/dev/null 2>&1; then
    printf '%s\n' 'This project already has an origin remote. Refusing to create another repository.' >&2
    exit 1
  fi
  if [[ "$(git branch --show-current)" != 'main' ]]; then
    printf '%s\n' 'Existing Git checkout must be on its main branch.' >&2
    exit 1
  fi
else
  git init -b main
fi
if [[ -z "$(git config user.name || true)" || -z "$(git config user.email || true)" ]]; then
  printf '%s\n' 'Set your Git author identity before publishing, for example:' >&2
  printf '%s\n' '  git config --global user.name "Your GitHub Display Name"' >&2
  printf '%s\n' '  git config --global user.email "YOUR_GITHUB_NOREPLY_EMAIL"' >&2
  exit 1
fi

# Explicit allowlist: do not stage imported profiles, databases or arbitrary local files.
git add -- \
  .gitignore LICENSE README.md CONTRIBUTING.md SECURITY.md \
  nbai.py install.sh uninstall.sh \
  docs/ARCHITECTURE.md docs/OPTIMIZATION.md \
  examples/antigravity_local_sdk.py tests/test_toolkit.py \
  .github/workflows/tests.yml scripts/publish-to-github.sh

git diff --cached --check
if ! git diff --cached --quiet; then
  git commit -m 'Initial release: local-first Ollama toolkit (MIT)'
fi

if ! git tag --list v1.0.0 | grep -qx v1.0.0; then
  git tag v1.0.0
fi

printf 'Creating PUBLIC repository %s from %s\n' "$repo" "$root"
gh repo create "$repo" --public --source="$root" --remote=origin --push \
  --description 'Portable local-first Ollama CLI, MCP tools, semantic search, and Linux diagnostics.'
git push origin v1.0.0
printf 'Published: https://github.com/%s\n' "$repo"
