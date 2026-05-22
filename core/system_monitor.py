"""시스템 리소스 모니터링 — GPU / CPU / RAM / 디스크."""
from __future__ import annotations

import subprocess
import urllib.request
import json

import psutil


def get_gpu_status() -> list[dict]:
    """nvidia-smi로 GPU 정보 반환. GPU 없거나 오류면 빈 리스트."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,temperature.gpu,power.draw,power.limit",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        )
        gpus = []
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 6:
                continue

            def _to_float(s: str) -> float | None:
                try:
                    return float(s)
                except ValueError:
                    return None

            gpus.append({
                "index":      int(parts[0]),
                "name":       parts[1],
                "util_pct":   _to_float(parts[2]),
                "temp_c":     _to_float(parts[3]),
                "power_w":    _to_float(parts[4]),
                "power_limit_w": _to_float(parts[5]),
            })
        return gpus
    except Exception:
        return []


def get_all_ollama_models(host: str = "http://localhost:11434") -> list[str]:
    """설치된 전체 Ollama 모델 목록 반환 (/api/tags)."""
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def load_ollama_model(model_name: str, host: str = "http://localhost:11434") -> bool:
    """모델을 VRAM에 로드 (keep_alive=-1 = 무기한 유지)."""
    try:
        payload = json.dumps({"model": model_name, "keep_alive": -1}).encode()
        req = urllib.request.Request(
            f"{host}/api/generate",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 200
    except Exception:
        return False


def unload_ollama_model(model_name: str, host: str = "http://localhost:11434") -> bool:
    """특정 모델을 VRAM에서 언로드 (keep_alive=0)."""
    try:
        payload = json.dumps({"model": model_name, "keep_alive": 0}).encode()
        req = urllib.request.Request(
            f"{host}/api/generate",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_ollama_vram(host: str = "http://localhost:11434") -> list[dict]:
    """Ollama /api/ps 에서 로드된 모델과 VRAM 점유량 반환."""
    try:
        with urllib.request.urlopen(f"{host}/api/ps", timeout=3) as resp:
            data = json.loads(resp.read())
        models = []
        for m in data.get("models", []):
            models.append({
                "name":       m.get("name", ""),
                "vram_gb":    m.get("size_vram", 0) / 1e9,
                "param_size": m.get("details", {}).get("parameter_size", ""),
                "quant":      m.get("details", {}).get("quantization_level", ""),
            })
        return models
    except Exception:
        return []


def get_system_status() -> dict:
    """CPU / RAM / 디스크 현황."""
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_pct":       psutil.cpu_percent(interval=0.3),
        "ram_used_gb":   vm.used / 1e9,
        "ram_total_gb":  vm.total / 1e9,
        "ram_pct":       vm.percent,
        "disk_used_gb":  disk.used / 1e9,
        "disk_total_gb": disk.total / 1e9,
        "disk_pct":      disk.percent,
    }
