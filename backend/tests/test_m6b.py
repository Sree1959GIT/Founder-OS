"""M6b: a re-run with a change already in the answer (HANDOVER next step 4) and the Kokoro engine choice."""

from __future__ import annotations

from typing import Any

from tests.test_voice_round2 import finished, lane
from tests.test_voice_round8 import answered, finance  # noqa: F401  (the fixture)


async def test_rerun_with_a_change_already_in_the_answer_reruns_only_that_agent(finance: Any) -> None:  # noqa: F811
    manager = lane(finance)
    first = await answered(manager)
    old = manager.orchestrator.runs[first.run_id or ""]
    again = await manager.turn(first.session_id, "Re-run the analyst, assume two hires.")
    assert again.started_run and again.run_id != first.run_id
    assert again.reply == (
        "That's already in this answer: it assumes two local hires. "
        "Re-running only the Financial Analyst again. The rest of the team's findings stand."
    )
    new_run = manager.orchestrator.runs[again.run_id or ""]
    assert new_run.message == old.message  # no change added to the request: the same decision
    new = await finished(manager, again.run_id)
    analyst = next(a for a in new.team if a.type == "financial_analyst")
    assert "The founder then added" not in analyst.brief


async def test_rerun_with_a_real_change_still_runs_the_whole_team(finance: Any) -> None:  # noqa: F811
    manager = lane(finance)
    first = await answered(manager)
    again = await manager.turn(first.session_id, "Re-run the analyst, assume three hires.")
    assert again.reply.startswith("That changes the decision, so the whole team runs again with it")
    await finished(manager, again.run_id)


# --- TTS latency: Kokoro on the GPU when it can be ------------------------------------------------------------------
def test_kokoro_goes_on_the_gpu_only_when_allowed_installed_and_not_int8() -> None:
    from app.config import Settings
    from app.voice.tts import CUDA_PROVIDER, gpu_wanted

    gpu = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    cpu = ["AzureExecutionProvider", "CPUExecutionProvider"]
    assert gpu_wanted("auto", "kokoro-v1.0.onnx", gpu)
    assert gpu_wanted("cuda", "kokoro-v1.0.onnx", gpu)
    assert not gpu_wanted("cpu", "kokoro-v1.0.onnx", gpu)
    assert not gpu_wanted("auto", "kokoro-v1.0.onnx", cpu)  # plain onnxruntime: the CPU, as in M5
    assert not gpu_wanted("cuda", "kokoro-v1.0.int8.onnx", gpu)  # int8 on CUDA measured 10-30 s a line
    assert CUDA_PROVIDER[1]["cudnn_conv_algo_search"] == "HEURISTIC"
    assert Settings(_env_file=None).voice_tts_device == "auto"


def test_enable_tts_gpu_swaps_the_package_and_undoes_it() -> None:
    from tests.test_packaging_scripts import load

    gpu = load("enable_tts_gpu")
    wheels = gpu.CUDA_WHEELS
    fresh = gpu.plan({"onnxruntime": "1.31.1"})
    assert fresh == [
        ["uninstall", "-y", "onnxruntime"],
        ["install", "--no-deps", "onnxruntime-gpu==1.23.2"],
        ["install", *wheels],
    ]
    done = {"onnxruntime-gpu": "1.23.2", **{w: "1" for w in wheels}}
    assert gpu.plan(done) == []
    # setup's pip install brought the CPU package back beside the GPU one: both go, the GPU one comes back alone
    assert gpu.plan({**done, "onnxruntime": "1.31.1"})[0] == ["uninstall", "-y", "onnxruntime", "onnxruntime-gpu"]
    assert gpu.plan(done, undo=True) == [
        ["uninstall", "-y", "onnxruntime-gpu"],
        ["install", "--force-reinstall", "--no-deps", "onnxruntime"],
    ]
    assert gpu.plan({"onnxruntime": "1.31.1"}, undo=True) == []
