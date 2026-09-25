"""OpenCode slash command plugin: /oc <prompt>."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

OPENCODE_BIN = (
    os.environ.get("OPENCODE_BIN")
    or shutil.which("opencode")
    or os.path.expanduser("~/.local/bin/opencode")
)
SERVER_URL = os.environ.get("OPENCODE_SERVER_URL", "http://127.0.0.1:4097")

_last_session_id: str | None = None


def _query_warm_server(text: str, session_id: str | None = None) -> tuple[str, str | None] | None:
    import urllib.request
    try:
        if not session_id:
            req = urllib.request.Request(
                f"{SERVER_URL}/session",
                data=json.dumps({}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                sess_info = json.loads(r.read().decode("utf-8"))
                session_id = sess_info.get("id")

        if not session_id:
            return None

        payload = {"parts": [{"type": "text", "text": text}]}
        req = urllib.request.Request(
            f"{SERVER_URL}/session/{session_id}/message",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=180) as r:
            res_data = json.loads(r.read().decode("utf-8"))
            parts = res_data.get("parts", [])
            text_chunks = [p.get("text", "") for p in parts if p.get("type") == "text" and p.get("text")]
            answer = "".join(text_chunks).strip()
            return answer or "(OpenCode returned an empty response)", session_id
    except Exception as e:
        logger.warning("Warm server query failed (%s), falling back to CLI", e)
        return None


def _query_cli(text: str, session_id: str | None = None) -> tuple[str, str | None]:
    cmd = [OPENCODE_BIN, "run", "--format", "json"]
    if session_id:
        cmd.extend(["-s", session_id])
    cmd.append(text)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return "Error: OpenCode timed out after 180s", session_id
    except Exception as e:
        return f"Error running OpenCode: {e}", session_id

    text_parts = []
    new_session_id = session_id
    for line in proc.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("sessionID"):
            new_session_id = event["sessionID"]
        part = event.get("part", {})
        if part.get("type") == "text" and part.get("text"):
            text_parts.append(part["text"])

    if not text_parts:
        if proc.returncode != 0 and proc.stderr:
            return f"OpenCode exited with code {proc.returncode}:\n{proc.stderr.strip()}", new_session_id
        return "(OpenCode returned an empty response)", new_session_id

    return "".join(text_parts).strip(), new_session_id


def _run_opencode_prompt(text: str, session_id: str | None = None) -> tuple[str, str | None]:
    # 1. Warm server (~1.5s)
    res = _query_warm_server(text, session_id=session_id)
    if res is not None:
        return res
    # 2. Cold CLI fallback
    return _query_cli(text, session_id=session_id)


def _handle_oc(raw_args: str) -> str:
    global _last_session_id
    if not raw_args or not raw_args.strip():
        return (
            "**OpenCode Slash Command**\n\n"
            "Usage: `/oc <prompt>`\n"
            "Subcommands:\n"
            "- `/oc reset` : Start a fresh OpenCode session\n"
            "- `/oc status`: Show current OpenCode session ID\n"
            "Example: `/oc explain what this repo does`"
        )

    arg = raw_args.strip()
    if arg == "reset":
        _last_session_id = None
        return "🔄 OpenCode session reset."
    elif arg == "status":
        if _last_session_id:
            return f"Active OpenCode session: `{_last_session_id}`"
        return "No active OpenCode session."

    reply, sess_id = _run_opencode_prompt(arg, session_id=_last_session_id)
    if sess_id:
        _last_session_id = sess_id
    return reply


def register(ctx) -> None:
    ctx.register_command(
        "oc",
        handler=_handle_oc,
        description="Directly query OpenCode. Usage: /oc <prompt>",
        args_hint="<prompt>"
    )
