#!/usr/bin/env python3
"""Collect MI355X kernel development versions without installing anything.

Usage: python3 mi355x-env-check.py [--smoke] [--repo PATH ...]
Prints JSON to stdout. --smoke runs a tiny torch GPU check, not a benchmark.
No secrets, environment dumps, network requests, or package changes.
"""
import argparse
import importlib
import importlib.metadata as metadata
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def command(args, cwd=None):
    try:
        result = subprocess.run(
            args, cwd=cwd, text=True, capture_output=True, timeout=25
        )
        return {"returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--repo", type=Path, action="append", default=[])
    args = parser.parse_args()
    report = {
        "platform": {"system": platform.system(), "kernel": platform.release(),
                     "machine": platform.machine()},
        "python": {"version": sys.version, "executable": sys.executable},
        "packages": {}, "imports": {}, "commands": {}, "repositories": [],
        "scope": "Version inventory; not a full-stack compatibility certification.",
    }
    distributions = (
        "torch", "amd-aiter", "flydsl", "triton", "pytorch-triton-rocm",
        "triton-rocm", "amd-triton", "pytorch-triton", "triton-kernels",
    )
    for name in distributions:
        try:
            report["packages"][name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            report["packages"][name] = None
    for name in ("torch", "triton", "flydsl", "aiter"):
        try:
            module = importlib.import_module(name)
            report["imports"][name] = {"version": getattr(module, "__version__", None),
                                       "file": getattr(module, "__file__", None)}
        except Exception as exc:
            report["imports"][name] = {"error": f"{type(exc).__name__}: {exc}"}

    for executable in ("hipcc", "cmake"):
        path = shutil.which(executable)
        if not path and executable == "hipcc" and Path("/opt/rocm/bin/hipcc").is_file():
            path = "/opt/rocm/bin/hipcc"
        report["commands"][executable] = command([path, "--version"]) if path else {"error": "not found"}
    for version_file in ("/opt/rocm/.info/version", "/opt/rocm/.info/version-dev"):
        path = Path(version_file)
        if path.is_file():
            report.setdefault("rocm_version_files", {})[version_file] = path.read_text().strip()

    try:
        import torch
        report["torch_hip"] = torch.version.hip
        report["gpu_available"] = torch.cuda.is_available()
        report["gpu_devices"] = []
        if report["gpu_available"]:
            for index in range(torch.cuda.device_count()):
                prop = torch.cuda.get_device_properties(index)
                report["gpu_devices"].append({
                    "index": index, "name": prop.name,
                    "arch": getattr(prop, "gcnArchName", None),
                    "total_memory_bytes": prop.total_memory,
                })
            if args.smoke:
                assert torch.version.hip is not None, "ROCm PyTorch required"
                assert "gfx950" in getattr(torch.cuda.get_device_properties(0), "gcnArchName", ""), "gfx950 required"
                x = torch.arange(256, dtype=torch.float32, device="cuda:0")
                y = x * 2 + 1
                torch.cuda.synchronize()
                torch.testing.assert_close(y.cpu(), torch.arange(256, dtype=torch.float32) * 2 + 1)
                report["smoke"] = "PASS: PyTorch elementwise correctness only"
        elif args.smoke:
            report["smoke"] = "SKIPPED: GPU unavailable"
    except Exception as exc:
        report["gpu_error"] = f"{type(exc).__name__}: {exc}"
        if args.smoke:
            report["smoke"] = "FAILED or unavailable; see gpu_error"

    try:
        import triton
        from triton.experimental import gluon
        from triton.experimental.gluon.language.amd import cdna4
        report["gluon"] = {"file": gluon.__file__, "cdna4": cdna4.__file__}
        if report.get("gpu_available"):
            report["triton_target"] = str(triton.runtime.driver.active.get_current_target())
    except Exception as exc:
        report["gluon"] = {"error": f"{type(exc).__name__}: {exc}"}

    for repo in args.repo:
        resolved = repo.resolve()
        report["repositories"].append({
            "path": str(resolved),
            "head": command(["git", "rev-parse", "HEAD"], cwd=resolved),
            "submodules": command(["git", "submodule", "status", "--recursive"], cwd=resolved),
            "status": command(["git", "status", "--short"], cwd=resolved),
        })
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.smoke and not str(report.get("smoke", "")).startswith("PASS"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
