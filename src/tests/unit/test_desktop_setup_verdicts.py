"""The setup screen's hardware probe and verdicts (desktop roadmap §4.4, §4.5; DT-2.1)."""
from __future__ import annotations

import json

import pytest

from app.models import catalog as model_catalog
from app.models import hardware
from app.models.verdicts import Installed, selection_size, verdicts

GB = 10**9


def _runner(outputs: dict[str, str | None]):
    def run(command: list[str]) -> str | None:
        joined = " ".join(command)
        for marker, output in outputs.items():
            if marker in joined:
                return output
        return None

    return run


def _facts(**changes):
    facts = {
        "platform": "windows-x64",
        "gpus": [{"name": "NVIDIA GeForce RTX 4080", "vendor": "nvidia", "vram_total_mb": 16376,
                  "vram_free_mb": 15000, "driver": "560.94"}],
        "adapters": [{"name": "NVIDIA GeForce RTX 4080", "vendor": "nvidia"}],
        "nvidia_driver": "560.94", "apple_silicon": False, "chip": "",
        "memory": {"total_bytes": 64 * 2**30, "available_bytes": 40 * 2**30, "commit_available_bytes": 60 * 2**30,
                   "commit_limit_bytes": 80 * 2**30},
        "disk": {"path": "C:/packs", "free_bytes": 400 * GB, "total_bytes": 1000 * GB},
    }
    facts.update(changes)
    return facts


def _runtime_bytes(runtime_id: str) -> int:
    return {"torch-windows-x64": int(2.5 * GB)}.get(runtime_id, int(0.2 * GB))


def _by_bundle(found):
    return {item.bundle: item for item in found}


@pytest.fixture(scope="module")
def shipped():
    return model_catalog.load()


def test_nvidia_smi_output_is_parsed(monkeypatch) -> None:
    monkeypatch.setattr(hardware, "_nvidia_smi", lambda: "nvidia-smi")
    run = _runner({"--query-gpu": "NVIDIA GeForce RTX 4090, 24564, 22816, 617.42\n"})
    assert hardware.nvidia_gpus(run) == [{"name": "NVIDIA GeForce RTX 4090", "vendor": "nvidia",
                                         "vram_total_mb": 24564, "vram_free_mb": 22816, "driver": "617.42"}]


def test_windows_adapters_name_the_vendor() -> None:
    run = _runner({"Win32_VideoController": json.dumps([{"Name": "AMD Radeon RX 7900 XTX"},
                                                        {"Name": "Intel(R) UHD Graphics 770"}])})
    assert [item["vendor"] for item in hardware.windows_adapters(run)] == ["amd", "intel"]


def test_the_probe_reads_apple_silicon_from_sysctl(tmp_path) -> None:
    run = _runner({"hw.optional.arm64": "1\n", "machdep.cpu.brand_string": "Apple M3 Pro\n",
                   "hw.memsize": str(36 * 2**30)})
    facts = hardware.probe(packs_folder=tmp_path, run=run, platform="macos-arm64")
    assert facts["apple_silicon"] is True and facts["chip"] == "Apple M3 Pro"
    assert facts["disk"]["free_bytes"] > 0


def test_a_machine_with_no_gpu_answers_without_raising(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(hardware, "_nvidia_smi", lambda: None)
    facts = hardware.probe(packs_folder=tmp_path, run=_runner({}), platform="windows-x64")
    assert facts["gpus"] == [] and facts["nvidia_driver"] == ""


def test_an_nvidia_pc_gets_the_recommended_voice_bundles(shipped) -> None:
    found = _by_bundle(verdicts(shipped, _facts(), Installed(), _runtime_bytes))
    assert found["voice-input"].status in {"fits", "warn"}
    assert found["voice-input"].runtimes == ["torch-windows-x64", "stt-windows-x64"]
    assert found["voice-input"].model_bytes == shipped.model("nemotron-speech-streaming-en-0.6b").size + \
        shipped.model("parakeet-realtime-eou-120m-v1").size


def test_an_amd_pc_sees_the_gpu_bundles_greyed_with_the_reason(shipped) -> None:
    facts = _facts(gpus=[], nvidia_driver="", adapters=[{"name": "AMD Radeon RX 7900 XTX", "vendor": "amd"}])
    found = _by_bundle(verdicts(shipped, facts, Installed(), _runtime_bytes))
    assert found["voice-output"].status == "unavailable"
    assert found["voice-output"].reasons == ["Needs an NVIDIA GPU (found AMD Radeon RX 7900 XTX)."]
    assert not any(item.recommended for item in found.values())


def test_an_old_driver_blocks_cuda_bundles_and_links_to_nvidia(shipped) -> None:
    facts = _facts(nvidia_driver="512.15")
    verdict = _by_bundle(verdicts(shipped, facts, Installed(), _runtime_bytes))["voice-output"]
    assert verdict.status == "unavailable" and "Update your NVIDIA driver" in verdict.reasons[0]
    assert verdict.action and verdict.action["url"].startswith("https://www.nvidia.com/")


def test_flux_warns_on_a_gpu_with_too_little_vram(shipped) -> None:
    facts = _facts(gpus=[{"name": "NVIDIA GeForce RTX 3060 Ti", "vendor": "nvidia", "vram_total_mb": 8192,
                          "vram_free_mb": 7000, "driver": "560.94"}])
    verdict = _by_bundle(verdicts(shipped, facts, Installed(), _runtime_bytes))["image-generation"]
    assert verdict.status == "warn" and "video memory" in verdict.reasons[0]
    assert not verdict.recommended


def test_a_mac_gets_parakeet_mlx_and_no_nvidia_bundles(shipped) -> None:
    facts = _facts(platform="macos-arm64", gpus=[], adapters=[], nvidia_driver="", apple_silicon=True)
    found = _by_bundle(verdicts(shipped, facts, Installed(), _runtime_bytes))
    assert found["voice-input"].status == "fits" and found["voice-input"].models == ["parakeet-tdt-0.6b-v3-mlx"]
    assert found["voice-output"].status == "fits"
    assert found["image-generation"].status == "unavailable"
    assert found["image-generation"].reasons == ["Not available on macOS."]


def test_too_little_disk_makes_a_bundle_unavailable(shipped) -> None:
    facts = _facts(disk={"path": "C:/", "free_bytes": 3 * GB, "total_bytes": 100 * GB})
    verdict = _by_bundle(verdicts(shipped, facts, Installed(), _runtime_bytes))["image-generation"]
    assert verdict.status == "unavailable" and "Not enough disk space" in verdict.reasons[-1]


def test_a_selection_counts_the_shared_torch_layer_once(shipped) -> None:
    size = selection_size(shipped, ["voice-input", "voice-output"], "windows-x64", Installed(), _runtime_bytes)
    assert size["runtime_bytes"] == int(2.5 * GB) + 2 * int(0.2 * GB)
    installed = Installed(runtimes=frozenset({"torch-windows-x64"}))
    size = selection_size(shipped, ["voice-output"], "windows-x64", installed, _runtime_bytes)
    assert size["runtime_bytes"] == int(0.2 * GB)


def test_installed_bundles_are_not_recommended_again(shipped) -> None:
    variant = shipped.bundle("voice-output").variant("windows-x64")
    installed = Installed(runtimes=frozenset({"torch-windows-x64", "tts-windows-x64"}),
                          models=frozenset(variant.models))
    verdict = _by_bundle(verdicts(shipped, _facts(), installed, _runtime_bytes))["voice-output"]
    assert verdict.installed and not verdict.recommended and verdict.model_bytes == 0
