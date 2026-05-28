"""
hardware_detect.py — Mimir Hardware Detection
Detects GPU, VRAM, and system RAM.
Returns a HardwareProfile used to recommend the appropriate model tier.
"""

import subprocess
import json
import re
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GPUInfo:
    name: str
    vendor: str  # "nvidia", "amd", "intel", "unknown"
    vram_gb: float
    vram_reliable: bool  # AMD/Intel WMI reporting can be inaccurate
    driver_version: Optional[str] = None


@dataclass
class HardwareProfile:
    gpus: list = field(default_factory=list)
    ram_gb: float = 0.0
    cpu_name: str = ""
    cpu_cores: int = 0
    detection_errors: list = field(default_factory=list)

    @property
    def primary_gpu(self) -> Optional[GPUInfo]:
        """Returns the highest-VRAM GPU, preferring NVIDIA."""
        nvidia = [g for g in self.gpus if g.vendor == "nvidia"]
        if nvidia:
            return max(nvidia, key=lambda g: g.vram_gb)
        if self.gpus:
            return max(self.gpus, key=lambda g: g.vram_gb)
        return None

    @property
    def best_vram_gb(self) -> float:
        gpu = self.primary_gpu
        return gpu.vram_gb if gpu else 0.0

    def recommend_tier(self) -> str:
        """Returns 'heavy', 'medium', or 'lite' based on detected hardware."""
        gpu = self.primary_gpu
        vram = self.best_vram_gb

        # Hard cap: if RAM is too low, always Lite
        if self.ram_gb < 16:
            return "lite"

        if gpu is None:
            return "lite"

        if gpu.vendor == "nvidia":
            if vram >= 24:
                return "heavy"
            elif vram >= 12:
                return "medium"
            else:
                return "lite"
        elif gpu.vendor in ("amd", "intel"):
            # WMI VRAM data is less reliable; be conservative
            if vram >= 16 and gpu.vram_reliable:
                return "medium"
            else:
                return "lite"
        else:
            return "lite"

    def get_performance_note(self, model_id: str) -> str:
        """Returns a human-readable performance expectation for a given model tier."""
        gpu = self.primary_gpu
        vram = self.best_vram_gb

        if model_id == "heavy":
            if gpu and gpu.vendor == "nvidia":
                if vram >= 48:
                    return "Full GPU acceleration. Expect 20–35 tokens/sec on this hardware."
                elif vram >= 24:
                    return "Full GPU acceleration. Expect 10–18 tokens/sec on this hardware."
                elif vram >= 16:
                    return "Partial offloading to system RAM. Expect 3–7 tokens/sec. Functional but slow."
                else:
                    return "Heavy CPU offloading required. Expect 1–2 tokens/sec or less. Not recommended."
            else:
                return "No NVIDIA GPU detected. This model will be very slow without GPU acceleration."

        elif model_id == "medium":
            if gpu and gpu.vendor == "nvidia":
                if vram >= 16:
                    return "Comfortable at this VRAM level. Expect 15–30 tokens/sec."
                elif vram >= 12:
                    return "Minor offloading to system RAM. Expect 10–20 tokens/sec — smooth for most use."
                elif vram >= 8:
                    return "Moderate offloading required. Expect 5–10 tokens/sec. Usable but not ideal."
                else:
                    return "Significant offloading at this VRAM level. Lite is a better fit for this machine."
            elif gpu and gpu.vendor in ("amd", "intel"):
                return "AMD/Intel acceleration support varies. Performance depends on driver version and ROCm compatibility."
            else:
                return "No GPU detected. This model will run slowly on CPU only."

        elif model_id == "lite":
            if gpu and gpu.vendor == "nvidia" and vram >= 8:
                return "GPU acceleration available for this model. Expect fast responses — 40–80 tokens/sec."
            elif self.ram_gb >= 16:
                return "Will run on CPU. Expect 10–20 tokens/sec on modern hardware with sufficient RAM."
            else:
                return "Will run on CPU. Responses will be slower on this hardware but functional."

        return "Performance data unavailable."


def _detect_nvidia() -> list:
    """Query nvidia-smi for GPU info. Returns list of GPUInfo objects."""
    gpus = []
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=8
        )
        if result.returncode != 0:
            return gpus

        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                continue
            name = parts[0]
            try:
                vram_mb = float(parts[1])
                vram_gb = round(vram_mb / 1024, 1)
            except (ValueError, IndexError):
                vram_gb = 0.0
            driver = parts[2] if len(parts) > 2 else None
            gpus.append(GPUInfo(
                name=name,
                vendor="nvidia",
                vram_gb=vram_gb,
                vram_reliable=True,
                driver_version=driver
            ))
    except FileNotFoundError:
        pass  # nvidia-smi not on PATH — no NVIDIA GPU or drivers not installed
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    return gpus


def _detect_via_powershell() -> list:
    """
    Query Win32_VideoController via PowerShell for AMD/Intel GPUs.
    Returns list of GPUInfo objects (excludes any NVIDIA already detected).
    """
    gpus = []
    ps_cmd = (
        "Get-WmiObject Win32_VideoController | "
        "Select-Object Name, AdapterRAM, DriverVersion | "
        "ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=12
        )
        if result.returncode != 0 or not result.stdout.strip():
            return gpus

        raw = result.stdout.strip()
        # PowerShell returns either a single object or array
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]

        for item in data:
            name = item.get("Name", "Unknown GPU")

            # Skip NVIDIA — handled by nvidia-smi above
            if "nvidia" in name.lower() or "geforce" in name.lower() or "quadro" in name.lower():
                continue

            adapter_ram = item.get("AdapterRAM")
            driver = item.get("DriverVersion")

            if adapter_ram is not None and adapter_ram > 0:
                vram_gb = round(adapter_ram / (1024 ** 3), 1)
                # WMI AdapterRAM is a 32-bit field — caps at ~4GB
                # If result is exactly 4.0GB, actual VRAM may be higher
                vram_reliable = vram_gb < 3.9
            else:
                vram_gb = 0.0
                vram_reliable = False

            if "amd" in name.lower() or "radeon" in name.lower():
                vendor = "amd"
            elif "intel" in name.lower() or "arc" in name.lower() or "iris" in name.lower():
                vendor = "intel"
            else:
                vendor = "unknown"

            # Skip software/virtual renderers
            if any(skip in name.lower() for skip in ["microsoft basic", "vmware", "virtualbox", "rdp"]):
                continue

            gpus.append(GPUInfo(
                name=name,
                vendor=vendor,
                vram_gb=vram_gb,
                vram_reliable=vram_reliable,
                driver_version=driver
            ))
    except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError):
        pass
    except Exception:
        pass
    return gpus


def _detect_ram() -> float:
    """Returns total system RAM in GB."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        return round(mem.total / (1024 ** 3), 1)
    except ImportError:
        pass

    # Fallback: PowerShell
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-WmiObject Win32_ComputerSystem).TotalPhysicalMemory"],
            capture_output=True, text=True, timeout=8
        )
        if result.returncode == 0:
            return round(int(result.stdout.strip()) / (1024 ** 3), 1)
    except Exception:
        pass
    return 0.0


def _detect_cpu() -> tuple:
    """Returns (cpu_name, core_count)."""
    try:
        import psutil
        cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 0
    except ImportError:
        cores = os.cpu_count() or 0

    # CPU name via platform or registry
    try:
        import platform
        cpu_name = platform.processor()
        if cpu_name:
            return cpu_name, cores
    except Exception:
        pass

    # Fallback: PowerShell
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-WmiObject Win32_Processor).Name"],
            capture_output=True, text=True, timeout=8
        )
        if result.returncode == 0:
            return result.stdout.strip(), cores
    except Exception:
        pass

    return "Unknown CPU", cores


def detect_hardware() -> HardwareProfile:
    """
    Main detection function. Runs all hardware checks and returns a HardwareProfile.
    Safe to call from a background thread.
    """
    profile = HardwareProfile()
    errors = []

    # NVIDIA first (most reliable source)
    try:
        nvidia_gpus = _detect_nvidia()
        profile.gpus.extend(nvidia_gpus)
    except Exception as e:
        errors.append(f"NVIDIA detection error: {e}")

    # AMD / Intel via PowerShell WMI
    try:
        other_gpus = _detect_via_powershell()
        profile.gpus.extend(other_gpus)
    except Exception as e:
        errors.append(f"WMI GPU detection error: {e}")

    # RAM
    try:
        profile.ram_gb = _detect_ram()
    except Exception as e:
        errors.append(f"RAM detection error: {e}")

    # CPU
    try:
        profile.cpu_name, profile.cpu_cores = _detect_cpu()
    except Exception as e:
        errors.append(f"CPU detection error: {e}")

    profile.detection_errors = errors
    return profile


def format_hardware_summary(profile: HardwareProfile) -> str:
    """Returns a one-line summary string for display in the UI."""
    parts = []

    gpu = profile.primary_gpu
    if gpu:
        vram_note = f"{gpu.vram_gb}GB VRAM"
        if not gpu.vram_reliable:
            vram_note += " (estimated)"
        parts.append(f"{gpu.name} — {vram_note}")
    else:
        parts.append("No discrete GPU detected")

    if profile.ram_gb > 0:
        parts.append(f"{profile.ram_gb}GB RAM")

    if profile.cpu_name:
        # Trim verbose CPU strings
        cpu = profile.cpu_name
        cpu = re.sub(r'\(R\)|\(TM\)|CPU @.*', '', cpu).strip()
        parts.append(cpu)

    return "   ·   ".join(parts)
