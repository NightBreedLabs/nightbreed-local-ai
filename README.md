# NightBreedLabs Local AI Toolkit (NBAI)

[![Tests](https://github.com/NightBreedLabs/nightbreed-local-ai/actions/workflows/tests.yml/badge.svg)](https://github.com/NightBreedLabs/nightbreed-local-ai/actions/workflows/tests.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A portable, **local-first** companion to an existing Ollama installation. Python 3.9+ standard library and Bash only. Designed around the user's Bazzite KDE / Niri + Homebrew Ollama environment, but works on most Linux distros with Python and a running Ollama server. It **does not install, replace, update, remove or restart Ollama**.

## What it includes

- `nbai doctor`: Ollama connectivity, installed binary, user-service and GPU prerequisites.
- `nbai status`: installed and loaded local/cloud tags.
- `nbai ask -m fast|code|reason`: role-routed local chat, optional file or stdin input.
- `nbai bench`: comparable per-model throughput and load timings.
- `nbai unload MODEL`: free model memory.
- `nbai profile balanced|coding|low-memory`: safe **previews** of optional tuning, no changes.
- `nbai profile-import FILE`: copy your full private knowledge base to a protected local file (permission 0600); **not included in the distributed archive**.
- `nbai index DIRECTORY`, `nbai search ...`, `nbai ask --grounded`: optional local semantic retrieval (requires `embeddinggemma` separately).
- `nbai mcp`: Python-only MCP stdio tools for Antigravity or any MCP-stdio client.
- `nbai mcp-install`: additive Antigravity MCP registration preserving existing servers, with a timestamped backup.
- `examples/antigravity_local_sdk.py`: optional demonstration of an Ollama-backed **Antigravity SDK agent** (independent of the Antigravity IDE model picker).

## Install on Bazzite KDE, Fedora, Ubuntu, Debian, Mint, Arch, or another Linux distro

Clone the repository or download and extract its source archive. In **Konsole or any Bash terminal**:

```bash
# After extracting to ~/Downloads/nightbreed-local-ai, or cloning it there:
mkdir -p "$HOME/.local/opt"
mv "$HOME/Downloads/nightbreed-local-ai" "$HOME/.local/opt/nightbreed-local-ai"  # adapt if extracted elsewhere
cd "$HOME/.local/opt/nightbreed-local-ai"
./install.sh
"$HOME/.local/bin/nbai" doctor
"$HOME/.local/bin/nbai" status
```

**Important:** If the extracted directory already lives somewhere else, `cd` there and run `./install.sh`; the symlink points to that directory. Keep the directory in its final location after installation. No sudo, Homebrew manipulation, pip or `rpm-ostree` needed. If Bash cannot find `nbai`, call `~/.local/bin/nbai` directly or ensure `~/.local/bin` is in `PATH`.

For the user's current setup, preserve `~/.local/bin/ollama`, `~/.config/systemd/user/ollama.service`, `~/.ollama/models`, `ollama-ctl`, existing `ollama` MCP, Noctalia's `ai-usagebar`, and Antigravity's local auth bridge. NBAI makes no changes to them.

## Use it

```bash
nbai ask -m fast 'Explain pipewire in 3 sentences'
nbai ask -m code 'Write a safe Bash script that counts MKV files'
nbai ask -m reason 'Compare two backup strategies for Linux'
cat some-script.sh | nbai ask -m code
nbai ask -m code --file ./script.py --ctx 8192
nbai bench --models 'llama3.2:3b,qwen2.5-coder:7b,deepseek-r1:8b' --runs 2 --ctx 4096
nbai unload qwen2.5-coder:7b
nbai profile coding
```

Everything above calls Ollama's **local loopback API**. Any model ending `:cloud` is blocked by this toolkit; it cannot unintentionally run your cloud-backed Gemma entry. The original `ollama` CLI remains available if you intentionally need cloud models. This toolkit deliberately does not connect to Antigravity's undocumented localhost auth bridge on port 32777.

## Optional shared document library

`local_docs_search` and `local_docs_ask` let any MCP client use the same [AnythingLLM](https://anythingllm.com/) library, so several assistants can share one set of reference documents and avoid cloud usage. Both talk only to a loopback AnythingLLM instance and only to workspaces in the `NBAI_DOCS_WORKSPACES` allowlist.

- `local_docs_search` returns sourced passages (8 by default) and uses no chat model. Read all of them, because the best passage is often not ranked first.
- `local_docs_ask` answers with a local model in a new session, so earlier answers cannot leak into its context. Local models can blend rules or cite the wrong section, so verify anything important with `local_docs_search`.

| Variable | Default | Purpose |
|---|---|---|
| `NBAI_DOCS_URL` | `http://127.0.0.1:3001` | Loopback AnythingLLM URL |
| `NBAI_DOCS_KEY_FILE` | `~/.local/share/anythingllm/agent-api.key` | Developer API key file, mode 600 |
| `NBAI_DOCS_WORKSPACES` | `benefits-research` | Comma-separated workspace allowlist; set this to your own workspaces |
| `NBAI_DOCS_IDLE_SECONDS` | `60` | Idle time before the service is stopped |

Passages are visible to the MCP client, so keep private material out of allowlisted workspaces when the client is cloud-connected.

## Load on demand

NBAI is built to leave no AI workload resident, which suits machines also used for gaming.

- `nbai ask` and the `local_*` model tools send `keep_alive: 0`, so a model unloads as soon as it answers.
- The docs tools start a user service named `anythingllm.service` when needed and schedule a stop after `NBAI_DOCS_IDLE_SECONDS`, using `systemd-run --user`. Do not enable that service at boot.
- Sandboxed clients without access to the user systemd bus cannot start the service; start it manually in that case.

## Add the optional Antigravity MCP server

```bash
nbai mcp-install --dry-run
nbai mcp-install
```

This **merges a new server named `nightbreed-local-ai`**, preserving your existing `ollama`, `rea`, Gemini docs, data-agent-kit, and science servers. It creates a permission-restricted backup if the config already existed. Antigravity's global MCP config is `~/.gemini/config/mcp_config.json`, also accessible under **Agent panel → … → MCP Servers → Manage MCP Servers → View raw config**. Refresh MCP servers afterward. This command does *not* test the user's actual Antigravity version; test tools after refreshing.

Available MCP tools: `local_fast`, `local_code`, `local_reason`, `local_models`, `local_search`, `local_docs_search`, and `local_docs_ask`. The two docs tools read allowlisted AnythingLLM workspaces (`NBAI_DOCS_WORKSPACES`) on loopback, so only put material in those workspaces that MCP clients may see. Since you already have an `ollama` MCP server, you can skip the new server if it doesn't add useful functions. `local_search` is *disabled by default* because returning snippets to a cloud-hosted MCP client could expose private context. For another MCP client, configure the same stdio command, using a real absolute path:

```json
{
  "mcpServers": {
    "nightbreed-local-ai": {
      "command": "/usr/bin/python3",
      "args": ["/home/YOU/.local/opt/nightbreed-local-ai/nbai.py", "mcp"]
    }
  }
}
```

Use `nbai mcp-install` instead of pasting the example: it resolves the correct Python and actual file path. MCP calls in Antigravity may be seen and logged by its *hosted* agent even though inference uses your local Ollama. **Local model inference is not the same as end-to-end privacy within a cloud-connected IDE.**

## Import the original Antigravity knowledge base privately

The source document contains personal contact/location data, so the distributable deliberately **does not ship the original knowledge base or any identifiers**. To use it on your own machine:

```bash
nbai profile-import "$HOME/Downloads/antigravity_complete_setup.md"
# Optional semantic indexing and retrieval (explicit local model download):
ollama pull embeddinggemma
nbai index "$HOME/.local/share/nbai/context"
nbai search 'What is my local Ollama model layout?'
nbai ask --grounded -m code 'How is my Ollama service configured?'
```

The original text is copied to `~/.local/share/nbai/context/private_profile.md` with 0600 permissions, and the context folder is 0700. The local index is saved as `~/.local/share/nbai/index.sqlite3` (0600). Search returns matching context snippets. The `--grounded` command inserts up to three relevant excerpts into a **local** Ollama prompt. This is not an always-on memory service; indexing is manual after source changes. **Read the profile before importing: remove tokens, passwords, and details not needed for the model.**

Semantic index also works on deliberately chosen code repositories, with a file count/size cap and exclusions for usual secrets, VCS, caches and dependencies. These exclusions are heuristics, not a guarantee that source files contain no secrets. A Git project is a natural index target:

```bash
nbai index "$HOME/nightbreedlabs/auto-epub-optimizer"
nbai search 'Where does the EPUB optimization happen?'
```

To enable MCP file-search responses **only if you accept the cloud client seeing snippets**, add `"env": {"NBAI_MCP_SEARCH_ENABLED":"1"}` to the `nightbreed-local-ai` MCP server entry. Keep it off for private knowledge bases. There is no remote server listener in NBAI, only stdio and local API calls.

## Optional: an actual local Ollama-backed Antigravity SDK agent

The **Antigravity SDK** offers `LocalOpenAIAgentConfig` with an Ollama `base_url` and `.lightweight()` tuning. It is separate from the regular Antigravity IDE model-selection menu. In a dedicated, user-owned Python virtual environment:

```bash
cd "$HOME/.local/opt/nightbreed-local-ai"
python3 -m venv .venv
.venv/bin/python -m pip install google-antigravity
.venv/bin/python examples/antigravity_local_sdk.py 'Explain the repository layout'
```

Install of the SDK requires network access and a compatible Python environment; it is **optional**, not required by NBAI. On a given machine, the SDK may vary in available tools, inference behavior, model tool-call quality, and supported operating systems. The example does not grant autonomous file changes, shell access or network privileges. Local 7B models may struggle with complex agentic tasks: use them for focused work and a larger cloud model for planning only when desired.

## Safe performance strategy for the Radeon 680M

1. Run `nbai doctor` and `ollama ps` while a model is processing to see the actual GPU/CPU placement.
2. Ollama's official ROCm Linux GPU list does **not** explicitly include the Radeon 680M. Vulkan adds support for some GPUs outside that list, but verify the runtime/backend exists in the **Homebrew binary**, the system's Vulkan driver works, and your measured `ollama ps` placement. Do not assume that `OLLAMA_IGPU_ENABLE=1` proves acceleration.
3. Keep `OLLAMA_NUM_PARALLEL=1`; simultaneous contexts amplify RAM use. Start with 4096 context for quick replies, 8192 for coding only where helpful. The `--ctx` request setting lets you compare without changing the service.
4. Benchmark warm and cold scenarios with `nbai bench`; compare wall time, eval tokens/sec, and load time. Avoid gaming during GPU benchmark tests.
5. If your current Vulkan/ROCm implementation supports Flash Attention, `OLLAMA_KV_CACHE_TYPE=q8_0` can reduce KV-cache memory at some precision cost. The service-wide setting is **opt-in** and not enabled by this project.
6. Your system has 32 GiB of shared RAM, not 32 GiB of dedicated VRAM. Two large models and a desktop game competing for shared memory can ruin responsiveness. Setting maximum loaded models to one and adjusting keep-alive may be worth testing, but preserve the existing baseline first.
7. `gemma4:cloud` is *not* a locally running 32B model. Prompt handling takes place on a remote endpoint when you deliberately invoke it.

See [docs/OPTIMIZATION.md](docs/OPTIMIZATION.md) for reversible user-service examples, [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for trust boundaries and portability, for the architecture and trust boundaries.

## Tests and uninstallation

```bash
python3 -m unittest discover -s tests -v
./uninstall.sh
```

Tests use a **fake Ollama server on a localhost ephemeral port**, with no actual local models. Manual validation against your live machine remains necessary. Uninstall removes only NBAI's symlink. Manually remove the additive MCP config entry if you installed it. Delete `~/.local/share/nbai` only if you want to erase imported profile and search index. Ollama, Homebrew, the user-service and models are untouched.

## Official documentation consulted (2026-10-30)

- https://docs.ollama.com/gpu
- https://docs.ollama.com/faq
- https://docs.ollama.com/api/chat
- https://docs.ollama.com/api/embed
- https://docs.ollama.com/api/openai-compatibility
- https://docs.ollama.com/cloud
- https://antigravity.google/docs/mcp
- https://antigravity.google/docs/sdk/local-models/
- https://antigravity.google/docs/sdk/overview/

No unsupported claims that the user's Homebrew build actually uses Vulkan/ROCm, or that this package has been run on the user's live desktop.

## Publishing and license

This is the source repository for [NightBreedLabs/nightbreed-local-ai](https://github.com/NightBreedLabs/nightbreed-local-ai). All project code and documentation are offered under the [MIT License](LICENSE), copyright (c) 2026 NightBreedLabs. This does **not** license Ollama, installed model weights, Antigravity, or third-party services. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

The maintainer can create the public repository from a fresh extracted release directory with `bash scripts/publish-to-github.sh`, provided `gh` and `git` are installed and GitHub CLI is authenticated with access to the NightBreedLabs organization. This publisher stages an explicit set of source files; it intentionally excludes the personal source profile. It does not modify existing GitHub repositories.
