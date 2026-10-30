# Architecture and privacy boundaries

```text
               ┌────────── Antigravity IDE / other MCP clients ──────────┐
               │  Agent model might run on a cloud provider             │
               └──────────────┬───────────────────────────────────────────┘
                              │ MCP stdio tools (opt-in installation)
                     ┌────────▼──────────┐
                     │ nbai.py MCP server│
                     └────────┬──────────┘
                              │ HTTP loopback only
Konsole/Bash ─────► nbai.py CLI ───► 127.0.0.1:11434 ───► Ollama
                     │  │                  (existing Homebrew or any install)
                     │  └► local SQLite embedding index
                     └────► private imported profile file (user-initiated)

Antigravity SDK example ──► Ollama OpenAI-compatible /v1 endpoint
```

## Trust boundaries

**CLI:** `nbai ask`, `nbai index`, `nbai search` and `nbai ask --grounded` talk only to a plain HTTP Ollama loopback endpoint and locally stored SQLite. Ollama itself *could* access the cloud when users choose cloud models, but NBAI blocks `:cloud` model calls. No model auto-downloads. Indexing a selected project creates an unencrypted local vector store: local filesystem permissions protect it from other ordinary users, not from root, a compromised account, or other processes under the same user.

**MCP:** The MCP client controls the prompt and sees the answer. Local computation **does not** prevent the client from passing the prompt and answer to an online model provider. `local_search` is disabled by default, because exposing indexed snippets is more sensitive than invoking models. Users must opt in explicitly via a config env var to expose search results. Do not index unredacted passwords, secrets, SSH keys, medical data or private correspondence without understanding the consequences.

**Antigravity SDK:** The provided optional example uses `LocalOpenAIAgentConfig` against the loopback endpoint. It is not a claim that Antigravity IDE's normal model picker supports arbitrary Ollama models. The separate SDK may use its own harness and file/tool policies; audit the package and prompts when extending it.

**Networking:** NBAI explicitly restricts its API URL to localhost/127.0.0.1/::1. It does not enable `OLLAMA_HOST=0.0.0.0`, proxy through Nginx, expose credentials from the Antigravity bridge (port 32777), or add firewall rules. A remote Ollama server is deliberately out of scope for the default security posture. Cross-distro portability means no mandatory systemd, Homebrew, Docker, GPU driver, pip dependency or distribution-specific package management.

**MCP configuration:** `nbai mcp-install` parses and merges an existing `mcp_config.json` object, preserving unrelated top-level fields and other `mcpServers` entries. If the name already exists with different content, it stops rather than overwriting it. It backs up the original before writing the new config with mode 0600; it does not save or print credentials from that config.

**Deletion:** `uninstall.sh` removes only the symlink if it points to the current code location. Existing Ollama service, Homebrew binaries and models are never changed. Indexed files and imported profile require deliberate deletion under `~/.local/share/nbai`.
