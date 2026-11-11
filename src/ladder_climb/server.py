"""Threaded, no-cache dashboard server using only the standard library."""
from __future__ import annotations

import ipaddress
import json
import socket
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from .schema import load_board

ASSETS = files("ladder_climb").joinpath("assets")
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


class DashboardServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    server_version = "LadderClimb/0.1"

    def __init__(self, *args, board_dir: Path, **kwargs):
        self.board_dir = board_dir
        super().__init__(*args, **kwargs)

    def _body(self, route: str) -> tuple[bytes, str] | None:
        if route in ("/", "/index.html"):
            return ASSETS.joinpath("dashboard.html").read_bytes(), CONTENT_TYPES[".html"]
        if route == "/ladder.json":
            path = self.board_dir / "ladder.json"
            return path.read_bytes(), CONTENT_TYPES[".json"] if path.is_file() else None
        if route == "/api/health":
            board = load_board(self.board_dir)
            payload = {
                "ok": True,
                "schema_version": board["schema_version"],
                "tracks": len(board["tracks"]),
                "rungs": sum(len(t["rungs"]) for t in board["tracks"].values()),
                "updated_at": board["updated_at"],
            }
            return json.dumps(payload).encode(), CONTENT_TYPES[".json"]
        if route.startswith("/assets/"):
            name = route.removeprefix("/assets/")
            if "/" not in name and name in {"dashboard.css", "dashboard.js", "charts.js"}:
                path = ASSETS.joinpath(name)
                return path.read_bytes(), CONTENT_TYPES[path.suffix]
        return None

    def _serve(self, include_body: bool = True) -> None:
        route = urlsplit(self.path).path
        try:
            response = self._body(route)
        except (OSError, ValueError):
            response = None
        if response is None:
            self.send_error(404 if route != "/api/health" else 503)
            return
        body, content_type = response
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def do_GET(self) -> None:
        self._serve()

    def do_HEAD(self) -> None:
        self._serve(False)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)


def make_server(directory: str | Path, host: str = "0.0.0.0", port: int = 18999) -> DashboardServer:
    root = Path(directory).expanduser().resolve()
    load_board(root)
    return DashboardServer((host, port), partial(Handler, board_dir=root))


def detected_addresses(host: str, port: int) -> list[tuple[str, str]]:
    if host not in ("0.0.0.0", "::"):
        return [(host, "local")]
    addresses = [("127.0.0.1", "localhost")]
    candidates: set[str] = set()
    try:
        candidates.update(item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None))
    except socket.gaierror:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("198.51.100.1", 9))
            candidates.add(probe.getsockname()[0])
    except OSError:
        pass
    for address in sorted(candidates):
        try:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
            if ip.is_loopback or ip.is_unspecified or ip.version != 4:
                continue
            kind = "tailnet" if ip in ipaddress.ip_network("100.64.0.0/10") else "LAN"
            addresses.append((address, kind))
        except ValueError:
            continue
    return list(dict.fromkeys(addresses))


def serve(directory: str | Path, host: str = "0.0.0.0", port: int = 18999) -> None:
    server = make_server(directory, host, port)
    actual_port = int(server.server_address[1])
    print("Dashboard URLs (share only on networks you trust):", flush=True)
    for address, kind in detected_addresses(host, actual_port):
        print(f"  {kind:9s} http://{address}:{actual_port}/", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
