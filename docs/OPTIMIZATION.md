# Performance and reversible tuning guide

## First: prove the current backend and speed

```bash
ollama --version
ollama list
nbai doctor
nbai bench --models 'llama3.2:3b,qwen2.5-coder:7b,deepseek-r1:8b' --ctx 4096
ollama ps
journalctl --user -u ollama.service -b --no-pager | grep -Ei 'gpu|vulkan|rocm|amdgpu|device|memory|runner' | tail -70
```

Run `ollama ps` during a model's response or before it unloads. `PROCESSOR` may show `100% CPU`, `100% GPU` or a split. The benchmark's `tokens_per_second` uses Ollama's `eval_count` and `eval_duration`, excluding prompt processing and cold model loading; compare `wall_seconds` for the user-facing impact.

To understand Vulkan availability on AMD Linux, inspect `vulkaninfo --summary` (if installed), GPU nodes at `/dev/dri/renderD*`, and Ollama's service logs. On Bazzite, prefer preinstalled Mesa/Vulkan rather than layering host packages without reason. The Ollama build needs Vulkan support itself. ROCm overrides such as `HSA_OVERRIDE_GFX_VERSION` can cause failures, and no such override is recommended here for the Radeon 680M.

## Your current environment vs possible changes

Current user-provided service: `OLLAMA_IGPU_ENABLE=1`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_KEEP_ALIVE=15m`. These are **reported settings**, not independently verified here. `OLLAMA_IGPU_ENABLE` is not established as a useful universal switch by the official GPU support page. `OLLAMA_FLASH_ATTENTION=1` cannot make an unsupported backend suddenly support Flash Attention.

Suggested **test-only** settings for a 32 GiB shared-memory workstation: `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_CONTEXT_LENGTH=4096` for lightweight requests, `OLLAMA_KV_CACHE_TYPE=q8_0` if Flash Attention supports it, and `OLLAMA_KEEP_ALIVE=5m` for a balance between quick reuse and releasing RAM. `nbai profile coding` prints a variant using 8192 context and 15m keep-alive.

## To trial an override without rewriting the working service

**Read your current unit first**:

```bash
systemctl --user cat ollama.service
systemctl --user show ollama.service -p FragmentPath -p DropInPaths
```

A possible test drop-in (do this *only after* validating a baseline, and do not include unnecessary vendor overrides):

```bash
mkdir -p ~/.config/systemd/user/ollama.service.d
cat > ~/.config/systemd/user/ollama.service.d/90-nbai-test.conf <<'EOF'
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_CONTEXT_LENGTH=4096"
Environment="OLLAMA_KEEP_ALIVE=5m"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
EOF
systemctl --user daemon-reload
systemctl --user restart ollama.service
```

This **restarts** Ollama and temporarily interrupts active requests, and `q8_0` is most useful when Flash Attention is available. Avoid doing it while actively using Antigravity. To revert your own test drop-in (only delete the file created above):

```bash
rm -- ~/.config/systemd/user/ollama.service.d/90-nbai-test.conf
systemctl --user daemon-reload
systemctl --user restart ollama.service
```

Do not remove `~/.config/systemd/user/ollama.service` or the Homebrew Ollama binary. On non-systemd systems, the same environment settings can be supplied to the process that starts `ollama serve`, after confirming the process owner and startup method.

## Memory and model strategy

- `llama3.2:3b`: fast, lower-memory general text.
- `qwen2.5-coder:7b`: first choice for shell and code tasks; measure 4096 vs 8192 context.
- `deepseek-r1:8b`: reasoning tasks; expect more latency and model overhead.
- `embeddinggemma`: optional purpose-built local embedding model for retrieval, not text conversation. Download only if you need semantic search: `ollama pull embeddinggemma`.
- `gemma4:cloud`: remote model through Ollama; avoid sending sensitive content to it unless you deliberately choose that workflow.

If the iGPU reports CPU-only or mixed allocation, don't chase marketing percentages. Confirm benchmark speed and system responsiveness. Increased VRAM reservations may take RAM from KDE/gaming while not significantly improving actual Ollama throughput. Cross-distro GPU packaging differs; no universal script should blindly install vendor ROCm drivers.
