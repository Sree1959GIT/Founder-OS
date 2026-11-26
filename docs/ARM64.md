# FounderOS on arm64 (for M7d: Oracle Cloud Always Free, Ampere A1)

M7d hosts FounderOS for Business Growth Academy members on an **Oracle Cloud Always Free Arm VM** (Ampere A1, arm64,
up to 4 OCPUs and 24 GB RAM, **no GPU**). This page records what runs on arm64 today. It was checked on **2026-11-22**
against PyPI, Docker Hub and Ollama's docs. Nothing here has run on the VM yet: M7d does that and updates this page.

## CI

`.github/workflows/ci.yml` job **`backend-arm64`** runs on GitHub's `ubuntu-24.04-arm` runner. It installs the backend
(`pip install -e ".[dev]"`, the same install as the x86 job) and runs the full `pytest` suite. The runner is free for
public repositories, and `Sree1959GIT/Founder-OS` is public. **If the repository goes private**, the job needs a plan
that includes Arm runners. Otherwise it waits in the queue and never starts, so remove the job or make it manual
(`workflow_dispatch`) rather than leaving CI red. The job covers the base install only. The `voice` and `gpu` extras are
covered in the table below.

## Component status

| Component | What FounderOS uses it for | arm64 status (2026-11-22) | Notes for the VM |
|---|---|---|---|
| **Ollama** | Qwen (`qwen3:8b`), `nomic-embed-text` | **Supported.** Ollama's Linux docs have an "ARM64 install" section (`ollama-linux-arm64.tar.zst`), and the install script picks it automatically. | CPU only on the A1 (no GPU). Expect a few tokens per second for `qwen3:8b` on 4 OCPUs. That is why the AI model card offers members cloud models, with Qwen as the free, private and slower default. Measure in M7d and consider a smaller model (`qwen3:4b`) for the fast lane. |
| **Qdrant** | Vector search (Docker) | **Supported.** The `qdrant/qdrant:latest` image is multi-arch (`amd64`, `arm64`) on Docker Hub. | `docker compose up -d qdrant` works unchanged. The in-memory fallback also needs no Docker. |
| **DuckDB** | The financial engine | **Supported.** `duckdb` 2.0.1 ships `manylinux` aarch64 wheels. | Part of the base install, so the `backend-arm64` CI job runs it. |
| **cryptography** (M7a) | Fernet for saved API keys | **Supported.** 50.0.2 ships aarch64 wheels. | Base install, covered by CI. |
| **faster-whisper / CTranslate2** | Speech to text (voice) | **Supported on CPU.** `faster-whisper` 1.2.1 is pure Python. `ctranslate2` 4.9.1 ships `manylinux_2_28` aarch64 wheels for CPython 3.10 to 3.12+. `av` and `tokenizers` have aarch64 wheels too. | No CUDA on the A1. Use `VOICE_STT_DEVICE=cpu` with `base.en` int8 (the CPU fallback). Voice latency on 4 Arm cores is not measured yet. The voice path stays on the server either way (it never goes to a cloud model). |
| **Kokoro / onnxruntime** | Text to speech (voice) | **Supported on CPU.** `kokoro-onnx` 0.6.1 is pure Python and needs `onnxruntime` (aarch64 wheels for 1.32.0), `espeakng-loader` (aarch64 wheel) and `phonemizer` (pure Python). Its GPU extra is x86_64 only. | `VOICE_TTS_DEVICE=cpu`. Do **not** run `scripts/enable_tts_gpu.py` there: it is for an NVIDIA GPU on Windows, and it skips itself when there is no GPU. |
| **torch** | Only the optional Laya fine-tuning and decision model (not installed by default) | **CPU wheels exist.** `torch` 2.15.0 ships aarch64 wheels on PyPI and on `download.pytorch.org/whl/cpu`. | Not needed on the hosted server (`DECISION_PROVIDER=llm`). Fine-tuning stays on the founder's GPU PC. |
| Frontend (Node 22, Vite) | The web app | **Supported.** Node publishes linux-arm64 builds. | Build once, then serve the static files behind Cloudflare. |

## What this means for M7d

- The backend's base install and tests run on arm64 (CI job `backend-arm64`).
- The VM has no GPU, so Qwen and voice run on the CPU and are slow. The M7a AI model card lets each member bring their
  own cloud key for the deep-work agents, with automatic fallback to Qwen.
- To check in M7d on the real VM: Ollama `qwen3:8b` tokens per second and RAM, a Whisper `base.en` and Kokoro CPU
  bench (`scripts/voice_bench.py`), Qdrant memory use, and `FOUNDEROS_SECRET_KEY` created by `setup.sh`
  (`scripts/ensure_secret.py`).
