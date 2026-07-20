from __future__ import annotations

import os
import subprocess
import sys
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class AdapterSpec:
    name: str
    repository: str
    import_module: str
    import_symbol: str


ADAPTER_SPECS = (
    AdapterSpec("docling", "third_party/docling", "docling.document_converter", "DocumentConverter"),
    AdapterSpec("mineru", "third_party/MinerU", "mineru.cli.common", "do_parse"),
    AdapterSpec("paddleocr", "third_party/PaddleOCR", "paddleocr", "PPStructureV3"),
)


def project_root() -> Path:
    configured = os.environ.get("PDF2WORD_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def resource_report(root: str | Path | None = None) -> dict[str, dict[str, object]]:
    base = Path(root).expanduser().resolve() if root else project_root()
    report = deepcopy(_static_resource_report(str(base)))
    enabled = os.environ.get("PDF2WORD_ENABLE_EXTERNAL_PARSERS") == "1"
    for status in report.values():
        status["enabled"] = enabled
    return report


@lru_cache(maxsize=4)
def _static_resource_report(root: str) -> dict[str, dict[str, object]]:
    base = Path(root)
    return {spec.name: _inspect_spec(spec, base) for spec in ADAPTER_SPECS}


def available_adapter_names(root: str | Path | None = None) -> set[str]:
    report = resource_report(root)
    return {
        name
        for name, status in report.items()
        if status.get("callable") is True and status.get("enabled") is True
    }


def _inspect_spec(spec: AdapterSpec, root: Path) -> dict[str, object]:
    repository = root / spec.repository
    cloned = (repository / ".git").is_dir() and (repository / "README.md").is_file()
    commit = _git_value(repository, "rev-parse", "HEAD") if cloned else None
    shallow = _git_value(repository, "rev-parse", "--is-shallow-repository") == "true" if cloned else None
    full_clone = bool(cloned and commit and shallow is False)
    runtime_importable, runtime_error = _probe_import(repository, spec)
    model_artifacts_cached = _model_artifacts_cached(spec)
    return {
        "repository": spec.repository,
        "cloned": cloned,
        "full_clone": full_clone,
        "commit": commit,
        "shallow": shallow,
        "import_module": spec.import_module,
        "import_symbol": spec.import_symbol,
        "runtime_importable": runtime_importable,
        "callable": bool(full_clone and runtime_importable),
        "enabled": False,
        "model_artifacts_cached": model_artifacts_cached,
        "runtime_error": runtime_error,
    }


def _git_value(repository: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


def _probe_import(repository: Path, spec: AdapterSpec) -> tuple[bool, str | None]:
    if not (repository / spec.import_module.split(".")[0]).exists():
        return False, "local package directory is missing"
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(part for part in (str(repository), existing) if part)
    probe = (
        "import importlib; "
        f"module = importlib.import_module({spec.import_module!r}); "
        f"getattr(module, {spec.import_symbol!r})"
    )
    try:
        subprocess.run(
            [sys.executable, "-c", probe],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return False, "runtime import probe timed out"
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "runtime import failed").strip().splitlines()
        return False, message[-1][:300] if message else "runtime import failed"
    except OSError as exc:
        return False, str(exc)
    return True, None


def _model_artifacts_cached(spec: AdapterSpec) -> bool | None:
    if spec.name != "docling":
        return None
    configured = os.environ.get("DOCLING_ARTIFACTS_PATH")
    roots = [Path(configured).expanduser()] if configured else [Path.home() / ".cache" / "docling"]
    return any(root.exists() and any(root.rglob("*.safetensors")) for root in roots)
