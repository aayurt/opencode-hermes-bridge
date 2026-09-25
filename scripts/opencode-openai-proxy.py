#!/usr/bin/env python3
"""OpenAI-compatible proxy for OpenCode.

Exposes an OpenAI /v1/chat/completions endpoint on http://127.0.0.1:4098
Uses warm OpenCode server (http://127.0.0.1:4097) for ~1s responses,
falling back to opencode CLI if the server is offline.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("opencode-proxy")

OPENCODE_BIN = (
    os.environ.get("OPENCODE_BIN")
    or shutil.which("opencode")
    or os.path.expanduser("~/.local/bin/opencode")
)
SERVER_URL = os.environ.get("OPENCODE_SERVER_URL", "http://127.0.0.1:4097")
PORT = int(os.environ.get("OPENCODE_PROXY_PORT", "4098"))

# Map conversation_key -> opencode_session_id
_SESSION_CACHE: dict[str, str] = {}


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text", ""))
            elif isinstance(p, str):
                parts.append(p)
        return "".join(parts)
    return str(content or "")


def _query_warm_server(prompt: str, session_id: str | None = None) -> tuple[str, str | None] | None:
    """Send prompt to warm OpenCode HTTP server for low latency (~1s)."""
    try:
        # Check / create session
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

        # Send message
        payload = {"parts": [{"type": "text", "text": prompt}]}
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
            return answer or "(Empty response)", session_id
    except Exception as e:
        logger.warning("Warm server request failed (%s), falling back to CLI", e)
        return None


def _query_cli(prompt: str, session_id: str | None = None) -> tuple[str, str | None]:
    cmd = [OPENCODE_BIN, "run", "--format", "json"]
    if session_id:
        cmd.extend(["-s", session_id])
    cmd.append(prompt)

    logger.info("Executing OpenCode CLI (session=%s): %s...", session_id, prompt[:60].replace("\n", " "))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return "Error: OpenCode timed out after 300 seconds.", session_id
    except Exception as e:
        return f"Error running OpenCode: {e}", session_id

    text_parts = []
    out_session_id = session_id
    for line in proc.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("sessionID"):
            out_session_id = event["sessionID"]
        part = event.get("part", {})
        if part.get("type") == "text" and part.get("text"):
            text_parts.append(part["text"])

    if not text_parts:
        if proc.returncode != 0 and proc.stderr:
            return f"OpenCode exited with error (code {proc.returncode}):\n{proc.stderr.strip()}", out_session_id
        return "(OpenCode returned an empty response)", out_session_id

    return "".join(text_parts).strip(), out_session_id


def _run_opencode(prompt: str, session_id: str | None = None) -> tuple[str, str | None]:
    # 1. Warm server (~1.5s)
    res = _query_warm_server(prompt, session_id=session_id)
    if res is not None:
        return res
    # 2. Cold CLI fallback
    return _query_cli(prompt, session_id=session_id)


class OpenCodeProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/health", "/"):
            self._send_json(200, {"status": "ok", "service": "opencode-openai-proxy", "port": PORT})
        elif path in ("/v1/models", "/models"):
            self._send_json(200, {
                "object": "list",
                "data": [
                    {
                        "id": "opencode",
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": "opencode"
                    }
                ]
            })
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/reset":
            _SESSION_CACHE.clear()
            self._send_json(200, {"status": "reset", "active_sessions": 0})
            return

        if path not in ("/v1/chat/completions", "/chat/completions"):
            self._send_json(404, {"error": "Endpoint not found"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        req_body = self.rfile.read(content_length)
        try:
            payload = json.loads(req_body.decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"error": f"Invalid JSON: {e}"})
            return

        messages = payload.get("messages", [])
        stream = bool(payload.get("stream", False))
        model_name = payload.get("model", "opencode")

        user_messages = [m for m in messages if m.get("role") == "user"]
        if not user_messages:
            self._send_json(400, {"error": "No user message found"})
            return

        first_user_text = _extract_text(user_messages[0].get("content", ""))
        conv_key = hashlib.sha256(first_user_text.encode("utf-8")).hexdigest()[:16]

        session_id = None
        if len(user_messages) > 1:
            session_id = _SESSION_CACHE.get(conv_key)

        latest_prompt = _extract_text(user_messages[-1].get("content", ""))
        answer, new_session_id = _run_opencode(latest_prompt, session_id=session_id)

        if new_session_id:
            _SESSION_CACHE[conv_key] = new_session_id

        created_ts = int(time.time())
        req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        if not stream:
            resp = {
                "id": req_id,
                "object": "chat.completion",
                "created": created_ts,
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": answer,
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": len(latest_prompt.split()),
                    "completion_tokens": len(answer.split()),
                    "total_tokens": len(latest_prompt.split()) + len(answer.split())
                }
            }
            self._send_json(200, resp)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            chunk1 = {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": answer},
                        "finish_reason": None
                    }
                ]
            }
            self.wfile.write(f"data: {json.dumps(chunk1)}\n\n".encode("utf-8"))

            chunk2 = {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }
                ]
            }
            self.wfile.write(f"data: {json.dumps(chunk2)}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), OpenCodeProxyHandler)
    logger.info("OpenCode OpenAI proxy listening on http://127.0.0.1:%d", PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down proxy...")
        server.shutdown()


if __name__ == "__main__":
    main()
