#!/usr/bin/env python3
"""Serve the MT tracker on this computer.

Save writes the three tracker files here, then copies them to
aliyun-hermes:/root/mt-tracker. The cloud machine does not serve the page.
"""

from __future__ import annotations

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parent
TOKEN_PATH = ROOT / ".token"
HOST = "127.0.0.1"
PORT = 8765
UPLOADS = (
    "session-history.json",
    "student-records.json",
    "praise-warning.md",
)
LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MT tracker</title>
</head>
<body>
  <h1>MT tracker</h1>
  <p>Type the save token to open the class list.</p>
  <form method="post" action="/">
    <label>Token <input name="token" type="password" autocomplete="current-password"></label>
    <button type="submit">Open</button>
  </form>
</body>
</html>
"""


def token() -> str:
    return TOKEN_PATH.read_text(encoding="utf-8").strip()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        if not TOKEN_PATH.exists():
            return True
        expected = token()
        if self.headers.get("X-MT-Token", "").strip() == expected:
            return True
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == "mt_session" and value.strip() == expected:
                return True
        return False

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/mt-tracker.html"):
            if not self._authorized():
                self._send(200, LOGIN_PAGE.encode("utf-8"), "text/html; charset=utf-8")
                return
            body = (ROOT / "mt-tracker.html").read_bytes()
            self._send(200, body, "text/html; charset=utf-8")
            return
        if self.path == "/api/state":
            if not self._authorized():
                self._send(401, b'{"error":"unauthorized"}', "application/json")
                return
            body = (ROOT / "session-history.json").read_bytes()
            self._send(200, body, "application/json; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if path == "/" and TOKEN_PATH.exists():
            given = (parse_qs(raw.decode("utf-8"), keep_blank_values=True).get("token") or [""])[0].strip()
            if given != token():
                self._send(401, LOGIN_PAGE.encode("utf-8"), "text/html; charset=utf-8")
                return
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header(
                "Set-Cookie",
                f"mt_session={given}; HttpOnly; Secure; SameSite=Strict; Path=/",
            )
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path != "/api/state":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        if not self._authorized():
            self._send(401, b'{"error":"unauthorized"}', "application/json")
            return
        payload = json.loads(raw.decode("utf-8"))
        (ROOT / "session-history.json").write_text(
            json.dumps(payload["history"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (ROOT / "student-records.json").write_text(
            json.dumps(payload["records"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (ROOT / "praise-warning.md").write_text(payload["markdown"], encoding="utf-8")
        if os.environ.get("MT_SKIP_UPLOAD") == "1":
            self._send(200, b'{"ok":true}', "application/json")
            return
        uploaded = subprocess.run(
            [
                "/usr/bin/scp",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=20",
                "-o",
                "IdentitiesOnly=yes",
                "-i",
                str(Path.home() / ".ssh/aliyun_ubuntu_uxsq"),
                "-o",
                "Ciphers=chacha20-poly1305@openssh.com",
                *[str(ROOT / name) for name in UPLOADS],
                "root@47.245.34.132:/root/mt-tracker/",
            ],
            capture_output=True,
            timeout=60,
            env={**os.environ, "HOME": str(Path.home()), "LANG": "en_US.UTF-8"},
        )
        if uploaded.returncode != 0:
            self._send(502, b'{"error":"upload failed"}', "application/json")
            return
        self._send(200, b'{"ok":true}', "application/json")

    def log_message(self, fmt: str, *args) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
