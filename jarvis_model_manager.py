"""Ollama model catalogue and lifecycle operations for J.A.R.V.I.S.

The GUI calls these functions from worker threads. Network traffic is sent to
Ollama's local API; model files remain in Ollama's own model store so app
updates do not redownload them.
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Any, Callable

import JARVIS as assistant

MODEL_TAG_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,100}$")
MODEL_CATALOGUE: tuple[dict[str, str], ...] = (
    {"name": "gemma4:e2b", "label": "Gemma 4 E2B", "description": "Recommended for 16 GB RAM PCs"},
    {"name": "gemma4:e4b", "label": "Gemma 4 E4B", "description": "More capable; needs more memory"},
    {"name": "gemma4:12b", "label": "Gemma 4 12B", "description": "Larger model; may be slow on older PCs"},
    {"name": "llama3.2:1b", "label": "Llama 3.2 1B", "description": "Very lightweight assistant model"},
    {"name": "llama3.2:3b", "label": "Llama 3.2 3B", "description": "Compact general-purpose model"},
    {"name": "qwen2.5:3b", "label": "Qwen 2.5 3B", "description": "Compact reasoning and coding model"},
)


def validate_model_tag(model: str) -> str:
    """Validate a model tag before including it in an API request."""
    name = str(model).strip()
    if not MODEL_TAG_RE.fullmatch(name) or name.startswith(("/", ".")) or ".." in name:
        raise ValueError("Enter a valid Ollama model tag, for example gemma4:e2b.")
    return name


def _active_host() -> str:
    # Ensure the local server is available before model-manager operations.
    assistant.ensure_ollama_available(timeout=12.0)
    return assistant._ollama_api_base()


def list_models() -> list[dict[str, Any]]:
    """Return installed models with safe display metadata."""
    _active_host()
    payload, _host = assistant._fetch_ollama_json("/api/tags", timeout=4.0)
    raw_models = payload.get("models", [])
    if not isinstance(raw_models, list):
        raise ValueError("Ollama returned an invalid model catalogue.")
    models: list[dict[str, Any]] = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("model")
        if not isinstance(name, str) or not name.strip():
            continue
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        size = item.get("size", 0)
        try:
            size_value = max(0, int(size))
        except (TypeError, ValueError, OverflowError):
            size_value = 0
        models.append({
            "name": name.strip(),
            "size": size_value,
            "parameter_size": str(details.get("parameter_size", "")),
            "quantization": str(details.get("quantization_level", "")),
            "family": str(details.get("family", "")),
        })
    return sorted(models, key=lambda row: row["name"].casefold())


def format_bytes(value: int) -> str:
    """Format a byte count for the model manager UI."""
    try:
        number = max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        number = 0
    if number >= 1024 ** 3:
        return f"{number / (1024 ** 3):.1f} GB"
    if number >= 1024 ** 2:
        return f"{number / (1024 ** 2):.0f} MB"
    if number >= 1024:
        return f"{number / 1024:.0f} KB"
    return f"{number} B"


def pull_model(
    model: str,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    *,
    timeout: float = 300.0,
) -> str:
    """Pull an Ollama model, streaming progress updates to a callback.

    The callback receives status, completed, total, and percentage keys. This
    function is blocking by design and must be run in a background worker.
    """
    name = validate_model_tag(model)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("The model download timeout must be positive.")
    host = _active_host()
    body = json.dumps({"model": name, "stream": True}).encode("utf-8")
    request = urllib.request.Request(
        host + "/api/pull",
        data=body,
        headers={
            "Accept": "application/x-ndjson, application/json",
            "Content-Type": "application/json",
            "User-Agent": f"JARVIS/{assistant.APP_VERSION}",
        },
        method="POST",
    )
    # _ollama_urlopen disables proxy inheritance for loopback API calls.
    with assistant._ollama_urlopen(request, timeout=float(timeout), base=host) as response:
        final_status = ""
        for raw_line in response:
            if not raw_line.strip():
                continue
            try:
                item = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise RuntimeError("Ollama returned an unreadable download-progress message.") from error
            if not isinstance(item, dict):
                continue
            if item.get("error"):
                raise RuntimeError(str(item["error"]))
            status = str(item.get("status", "Downloading model"))
            completed = item.get("completed", 0)
            total = item.get("total", 0)
            try:
                completed_value = max(0, int(completed))
                total_value = max(0, int(total))
            except (TypeError, ValueError, OverflowError):
                completed_value, total_value = 0, 0
            percent = min(100, int(completed_value * 100 / total_value)) if total_value else 0
            final_status = status
            if progress_callback:
                progress_callback({
                    "model": name,
                    "status": status,
                    "completed": completed_value,
                    "total": total_value,
                    "percent": percent,
                })
        if final_status.casefold() not in {"success", "completed"}:
            # Some Ollama builds finish the stream with no explicit success
            # marker. Confirm the model is installed rather than guessing.
            installed = {row["name"].casefold() for row in list_models()}
            if name.casefold() not in installed:
                raise RuntimeError(f"Ollama ended the download stream before {name} was confirmed installed.")
    return name


def delete_model(model: str) -> str:
    """Delete an installed model from Ollama's local model store."""
    name = validate_model_tag(model)
    host = _active_host()
    request = urllib.request.Request(
        host + "/api/delete",
        data=json.dumps({"model": name}).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"JARVIS/{assistant.APP_VERSION}",
        },
        method="DELETE",
    )
    with assistant._ollama_urlopen(request, timeout=20.0, base=host) as response:
        if response.status not in (200, 202, 204):
            raise RuntimeError(f"Ollama returned HTTP {response.status} while deleting {name}.")
        # Read the response to ensure transport errors are surfaced.
        response.read(1024 * 1024)
    return name
