"""Thin MiniMax chat-completions client — stdlib only. Key from env; NEVER logged.

OpenAI-compatible request shape. Override endpoint/model via MINIMAX_BASE_URL /
MINIMAX_MODEL if MiniMax's API path differs from the default."""
import json
import os
import urllib.request

DEFAULT_MODEL = "MiniMax-M3"
DEFAULT_BASE = "https://api.minimax.io/v1"


def complete(prompt, *, model=None, key=None, base_url=None, timeout=600):
    key = key or os.environ.get("MINIMAX_API_KEY")
    if not key:
        raise RuntimeError("MINIMAX_API_KEY not set")
    model = model or os.environ.get("MINIMAX_MODEL", DEFAULT_MODEL)
    base = (base_url or os.environ.get("MINIMAX_BASE_URL", DEFAULT_BASE)).rstrip("/")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        base + "/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]
