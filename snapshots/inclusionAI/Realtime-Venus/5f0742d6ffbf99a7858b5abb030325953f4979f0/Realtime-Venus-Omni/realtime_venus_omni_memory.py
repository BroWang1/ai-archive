# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Load the Realtime-Venus-Omni memory package from a model directory or Hub repository.

Resolve memory_adapter beside the model files and load one package instance
per directory. For Hub models, retrieve the package source from the same
repository revision.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import threading
from types import ModuleType
from typing import Any


_RUNTIME_MODULES: dict[Path, ModuleType] = {}
_LOAD_LOCK = threading.Lock()


def _model_source(model: Any) -> tuple[str, str | None]:
    """Return the local model path or Hub repository id and optional revision."""
    config = getattr(model, "config", None)
    source = getattr(config, "_name_or_path", None)
    if not isinstance(source, str) or not source.strip():
        source = getattr(model, "name_or_path", None)
    if not isinstance(source, str) or not source.strip():
        raise RuntimeError(
            "cannot locate memory_adapter: model.config._name_or_path is empty"
        )
    revision = getattr(config, "_commit_hash", None)
    if revision is not None and not isinstance(revision, str):
        revision = None
    return source.strip(), revision


def _resolve_adapter_directory(model: Any) -> Path:
    """Resolve the memory package in a local directory or Hub source snapshot."""
    source, revision = _model_source(model)
    local_source = Path(source).expanduser()
    if local_source.is_dir():
        adapter = (local_source / "memory_adapter").resolve()
    else:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as error:
            raise RuntimeError(
                "loading Memory from a Hub model requires huggingface_hub"
            ) from error
        snapshot = snapshot_download(
            repo_id=source,
            revision=revision,
            allow_patterns="memory_adapter/**",
        )
        adapter = (Path(snapshot) / "memory_adapter").resolve()
    if not (adapter / "__init__.py").is_file():
        raise RuntimeError(
            f"Memory adapter package is missing from model repository: {adapter}"
        )
    return adapter


def _load_runtime(model: Any) -> ModuleType:
    """Load and cache one package instance per resolved memory directory."""
    adapter = _resolve_adapter_directory(model)
    with _LOAD_LOCK:
        loaded = _RUNTIME_MODULES.get(adapter)
        if loaded is not None:
            return loaded
        module_name = f"_realtime_venus_omni_memory_adapter_runtime_{len(_RUNTIME_MODULES) + 1}"
        spec = importlib.util.spec_from_file_location(
            module_name,
            adapter / "__init__.py",
            submodule_search_locations=[str(adapter)],
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot import Memory adapter package: {adapter}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        _RUNTIME_MODULES[adapter] = module
        return module


def configure_memory(model: Any, *, memory_minutes: float | None = None) -> Any:
    """Configure Memory with an optional Duplex archive duration in minutes."""
    return _load_runtime(model).configure_memory(model, memory_minutes=memory_minutes)


__all__ = ["configure_memory"]
