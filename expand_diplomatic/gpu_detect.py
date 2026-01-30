"""Detect high-end GPUs for aggressive local training protocol."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


def _is_on_ac_power() -> bool:
    """True if on AC/mains power; False if battery-only or unknown."""
    v = os.environ.get("EXPANDER_AGGRESSIVE_ON_BATTERY", "").strip().lower()
    if v in ("1", "true", "yes"):
        return True  # User override: allow aggressive on battery
    if sys.platform == "darwin":
        try:
            r = subprocess.run(
                ["pmset", "-g", "batt"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if r.returncode == 0 and "AC Power" in r.stdout:
                return True
            return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class SYSTEM_POWER_STATUS(ctypes.Structure):
                _fields_ = [
                    ("ACLineStatus", wintypes.BYTE),
                    ("BatteryFlag", wintypes.BYTE),
                    ("BatteryLifePercent", wintypes.BYTE),
                    ("Reserved1", wintypes.BYTE),
                    ("BatteryLifeTime", wintypes.DWORD),
                    ("BatteryFullLifeTime", wintypes.DWORD),
                ]

            sps = SYSTEM_POWER_STATUS()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps)):
                return sps.ACLineStatus == 1  # 1=online, 0=battery, 255=unknown
        except Exception:
            pass
        return False
    # Linux: check /sys/class/power_supply
    try:
        ac_paths = [
            "/sys/class/power_supply/AC/online",
            "/sys/class/power_supply/AC0/online",
        ]
        for p in ac_paths:
            try:
                with open(p, encoding="utf-8") as f:
                    return f.read().strip() == "1"
            except OSError:
                continue
        # No AC supply reported (e.g. laptop on battery)
        return False
    except Exception:
        return False


def detect_high_end_gpu() -> bool:
    """
    Detect if a high-end GPU is available and on AC power.
    Aggressive local training is disabled when on battery to avoid drain.

    Env override:
      EXPANDER_AGGRESSIVE_LOCAL=1  force on (even on battery)
      EXPANDER_AGGRESSIVE_LOCAL=0  force off
      EXPANDER_AGGRESSIVE_ON_BATTERY=1  allow aggressive when on battery (if GPU ok)
    """
    v = os.environ.get("EXPANDER_AGGRESSIVE_LOCAL", "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    if not _is_on_ac_power():
        return False

    threshold_mb = 8192  # 8GB
    v_mb = os.environ.get("EXPANDER_GPU_VRAM_MB", "").strip()
    if v_mb:
        try:
            threshold_mb = max(1024, int(v_mb))
        except ValueError:
            pass

    return _check_nvidia_vram(threshold_mb) or _check_amd_vram(threshold_mb)


def _check_nvidia_vram(threshold_mb: int) -> bool:
    """NVIDIA GPU via nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0 or not result.stdout.strip():
        return False
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.replace("MiB", "").replace("MB", "").split()
        if parts:
            try:
                if int(parts[0]) >= threshold_mb:
                    return True
            except ValueError:
                pass
    return False


def _check_amd_vram(threshold_mb: int) -> bool:
    """AMD GPU via rocm-smi, amd-smi, or Linux sysfs."""
    # Try rocm-smi (ROCm)
    for cmd in ["rocm-smi", "/opt/rocm/bin/rocm-smi"]:
        try:
            result = subprocess.run(
                [cmd, "--showmeminfo", "vram"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0 or not result.stdout:
            continue
        # Parse "GPU[0]         : 8176 MiB" or "vram_total (MB): 8192"
        for match in re.finditer(r"(\d+)\s*(?:MiB|MB|M)", result.stdout, re.IGNORECASE):
            try:
                val = int(match.group(1))
                if val >= threshold_mb:
                    return True
            except ValueError:
                pass
        # Also try --showmemuse (shows "GPU memory: 1024 MiB")
        try:
            r2 = subprocess.run(
                [cmd, "--showmemuse"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        else:
            if r2.returncode == 0 and r2.stdout:
                for m in re.finditer(r"(\d+)\s*(?:MiB|MB|M)", r2.stdout, re.IGNORECASE):
                    try:
                        if int(m.group(1)) >= threshold_mb:
                            return True
                    except ValueError:
                        pass
    # Try amd-smi (newer AMD tool)
    try:
        r = subprocess.run(
            ["amd-smi", "info", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    else:
        if r.returncode == 0 and r.stdout:
            for m in re.finditer(r"(\d+)\s*(?:MiB|MB|M)", r.stdout, re.IGNORECASE):
                try:
                    if int(m.group(1)) >= threshold_mb:
                        return True
                except ValueError:
                    pass
    # Linux sysfs: AMD amdgpu driver
    if sys.platform == "linux":
        try:
            for p in Path("/sys/class/drm").glob("card*/device/mem_info_vram_total"):
                try:
                    total_bytes = int(p.read_text().strip())
                    total_mb = total_bytes // (1024 * 1024)
                    if total_mb >= threshold_mb:
                        return True
                except (OSError, ValueError):
                    continue
        except Exception:
            pass
    return False
