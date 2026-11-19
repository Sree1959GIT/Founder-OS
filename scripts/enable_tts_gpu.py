"""Kokoro on the GPU (M6b): swap onnxruntime for onnxruntime-gpu in this venv, with the CUDA 12 DLLs it needs.

    python scripts/enable_tts_gpu.py            do it (skipped when there is no NVIDIA GPU, or when already done)
    python scripts/enable_tts_gpu.py --check    only report
    python scripts/enable_tts_gpu.py --undo     back to plain onnxruntime (Kokoro on the CPU, the M5 set-up)

Why a script: faster-whisper and kokoro-onnx both depend on the package named `onnxruntime`, and `onnxruntime-gpu`
installs into the same folder. Installed side by side, whichever came last wins file by file. So the CPU package is
removed and the GPU one installed without dependencies. setup.bat runs this after every `pip install`, because that
install brings the CPU package back.

The version is pinned to 1.23.2: measured on the founder's PC, its CUDA provider loads with the CUDA 12 / cuDNN 9 DLLs
that Whisper (CTranslate2) already uses. 1.31.1 needs CUDA 13 (cublasLt64_13.dll), which would add about 1 GB more.
Silero VAD keeps running on the CPU provider, which onnxruntime-gpu includes. Nothing fails setup: on any problem the
CPU package is put back and a warning printed.
"""

from __future__ import annotations

import argparse
import contextlib
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GPU_PACKAGE = "onnxruntime-gpu"
GPU_VERSION = "1.23.2"
CPU_PACKAGE = "onnxruntime"
# cuBLAS and cuDNN come with backend[gpu] (Whisper); the CUDA provider of onnxruntime also loads these three.
CUDA_WHEELS = ["nvidia-cuda-runtime-cu12", "nvidia-cufft-cu12", "nvidia-curand-cu12"]

# "Available" is not enough (a CUDA 13 build lists the provider and then cannot load it): a real session must start
# on CUDA. The small Silero model bundled in faster-whisper is the test model.
CHECK = """
import sys
from pathlib import Path
sys.path.insert(0, "backend")
from app.voice.stt import add_cuda_dll_dirs
add_cuda_dll_dirs()
import faster_whisper, onnxruntime as ort
ok = False
if "CUDAExecutionProvider" in ort.get_available_providers():
    model = Path(faster_whisper.__file__).parent / "assets" / "silero_vad_v6.onnx"
    try:
        s = ort.InferenceSession(str(model), providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        ok = s.get_providers()[0] == "CUDAExecutionProvider"
    except Exception:
        ok = False
print(ort.__version__, ok)
"""


def installed() -> dict[str, str]:
    found: dict[str, str] = {}
    for name in [CPU_PACKAGE, GPU_PACKAGE, *CUDA_WHEELS]:
        with contextlib.suppress(metadata.PackageNotFoundError):
            found[name] = metadata.version(name)
    return found


def plan(have: dict[str, str], *, undo: bool = False) -> list[list[str]]:
    """The pip commands (arguments after `pip`) that reach the wanted state from `have`; [] when already there."""
    if undo:
        if GPU_PACKAGE not in have and CPU_PACKAGE in have:
            return []
        steps = [["uninstall", "-y", GPU_PACKAGE]] if GPU_PACKAGE in have else []
        return [*steps, ["install", "--force-reinstall", "--no-deps", CPU_PACKAGE]]
    done = have.get(GPU_PACKAGE) == GPU_VERSION and CPU_PACKAGE not in have and all(w in have for w in CUDA_WHEELS)
    if done:
        return []
    steps: list[list[str]] = []
    gone = [p for p in (CPU_PACKAGE, GPU_PACKAGE) if p in have]
    if gone:
        steps.append(["uninstall", "-y", *gone])
    steps.append(["install", "--no-deps", f"{GPU_PACKAGE}=={GPU_VERSION}"])
    missing = [w for w in CUDA_WHEELS if w not in have]
    if missing:
        steps.append(["install", *missing])
    return steps


def has_nvidia_gpu() -> bool:
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return False
    try:
        return subprocess.run([exe, "-L"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def pip(args: list[str]) -> bool:
    print("  pip", " ".join(args))
    return subprocess.run([sys.executable, "-m", "pip", *args]).returncode == 0


def cuda_works() -> tuple[str, bool]:
    out = subprocess.run([sys.executable, "-c", CHECK], capture_output=True, text=True, timeout=120, cwd=ROOT)
    words = (out.stdout.strip().splitlines() or [""])[-1].split()
    return (words[0] if words else "?"), (len(words) > 1 and words[1] == "True")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only report")
    parser.add_argument("--undo", action="store_true", help="back to plain onnxruntime (Kokoro on the CPU)")
    args = parser.parse_args()
    have = installed()
    print("onnxruntime packages:", ", ".join(f"{k} {v}" for k, v in have.items()) or "none")
    if args.check:
        version, ok = cuda_works() if have else ("none", False)
        print(f"[{'OK' if ok else 'INFO'}] onnxruntime {version}: Kokoro on the {'GPU' if ok else 'CPU'}")
        return 0
    if not args.undo and not has_nvidia_gpu():
        print("[INFO] No NVIDIA GPU found: Kokoro stays on the CPU.")
        return 0
    steps = plan(have, undo=args.undo)
    if not steps:
        print("[OK] Nothing to change.")
    for step in steps:
        if not pip(step):
            print("[WARN] pip failed; putting plain onnxruntime back so voice keeps working on the CPU.")
            for back in plan(installed(), undo=True):
                pip(back)
            return 0
    if args.undo:
        print("[OK] Kokoro runs on the CPU.")
        return 0
    version, ok = cuda_works()
    if ok:
        print(f"[OK] onnxruntime-gpu {version}: Kokoro will run on the GPU (VOICE_TTS_DEVICE=auto).")
    else:
        print(f"[WARN] onnxruntime {version} has no working CUDA provider: Kokoro falls back to the CPU at start-up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
