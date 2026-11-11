"""Read-only threaded HTTP API and self-contained dashboard server."""
from __future__ import annotations
import ipaddress, json, re, socket
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .history import export_history, history_payload
from .schema import ValidationError, champion, load_board, normalize_board, utc_now
from .store import list_campaigns, list_models, paths_for
ASSETS = files("ladder_climb").joinpath("assets")
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}
FILTERS = {"model", "campaign", "track", "status", "gate", "review", "search", "session", "wave", "since", "until", "sort"}
class RequestError(ValueError):
    def __init__(self, status: int, message: str): self.status, self.message = status, message
class DashboardServer(ThreadingHTTPServer):
    allow_reuse_address = True; daemon_threads = True

def _json_bytes(value: object) -> tuple[bytes, str]: return json.dumps(value, ensure_ascii=False).encode(), CONTENT_TYPES[".json"]
def _card(root: Path, model: dict) -> dict:
    board = load_board(paths_for(root, None if model["id"] == "legacy" else model["id"]).feed.parent)
    champions = {}
    for key, track in board["tracks"].items():
        best, winner = champion(track); baseline = track.get("baseline")
        champions[key] = {"value": best, "unit": track["unit"], "rung_id": winner["id"] if winner else None,
            "gain": best / baseline if best is not None and baseline not in (None, 0) else None}
    return dict(model, title=board["title"], updated_at=board["updated_at"], revision=board.get("revision", 0),
        testing=sum(r["status"] == "testing" for t in board["tracks"].values() for r in t["rungs"]), champions=champions,
        campaigns=list_campaigns(root, model["id"]) if model["id"] != "legacy" else [])
class Handler(BaseHTTPRequestHandler):
    server_version = "LadderClimb/0.2"
    def __init__(self, *args, root: Path, model: str | None, campaign: str | None, cors: bool, token: str | None, **kwargs):
        self.root, self.model, self.campaign, self.cors, self.token = root, model, campaign, cors, token
        super().__init__(*args, **kwargs)
    def _query(self) -> dict[str, str]:
        values = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        return {key: val[-1] for key, val in values.items()}
    def _selected_board(self) -> dict:
        return load_board(paths_for(self.root, self.model, self.campaign).feed.parent)
    def _body(self, route: str) -> tuple[bytes, str]:
        query = self._query()
        if route in ("/", "/index.html"): return ASSETS.joinpath("dashboard.html").read_bytes(), CONTENT_TYPES[".html"]
        if route == "/ladder.json":
            path = paths_for(self.root, self.model, self.campaign).feed
            if (self.root / "ladder.json").is_file() and not self.model and not self.campaign:
                raw = json.loads(path.read_text(encoding="utf-8")); return _json_bytes(dict(normalize_board(raw), now=utc_now()))
            return _json_bytes(dict(self._selected_board(), now=utc_now()))
        if route == "/api/health":
            board = self._selected_board()
            return _json_bytes({"ok": True, "now": utc_now(), "schema_version": board["schema_version"], "tracks": len(board["tracks"]),
                "rungs": sum(len(t["rungs"]) for t in board["tracks"].values()), "updated_at": board["updated_at"], "revision": board.get("revision", 0)})
        if route == "/api/workspace":
            models = [_card(self.root, model) for model in list_models(self.root)]
            return _json_bytes({"schema_version": 2, "now": utc_now(), "default_model": self.model or (models[0]["id"] if models else None), "models": models})
        match = re.fullmatch(r"/api/models/([A-Za-z0-9_.-]+)/ladder\.json", route)
        if match:
            if match.group(1) not in {m["id"] for m in list_models(self.root)}: raise RequestError(404, "unknown model")
            board = load_board(paths_for(self.root, match.group(1), query.get("campaign")).feed.parent)
            return _json_bytes(dict(board, now=utc_now()))
        match = re.fullmatch(r"/api/models/([A-Za-z0-9_.-]+)/campaigns", route)
        if match:
            if match.group(1) not in {m["id"] for m in list_models(self.root)}: raise RequestError(404, "unknown model")
            return _json_bytes({"now": utc_now(), "campaigns": list_campaigns(self.root, match.group(1))})
        if route in ("/api/history", "/api/export"):
            unknown = set(query) - FILTERS - {"limit", "offset", "cursor", "format"}
            if unknown: raise RequestError(400, "unknown filter: " + ", ".join(sorted(unknown)))
            filters = {key: query[key] for key in FILTERS if key in query}
            if filters.get("sort", "newest") not in ("newest", "chronological"): raise RequestError(400, "invalid sort")
            if route == "/api/export":
                fmt = query.get("format", "json")
                if fmt not in ("json", "csv"): raise RequestError(400, "invalid format")
                content, content_type = export_history(self.root, fmt, filters); return content.encode(), content_type
            try: limit, offset = int(query.get("limit", 500)), int(query.get("offset", 0))
            except ValueError as exc: raise RequestError(400, "invalid pagination") from exc
            return _json_bytes(history_payload(self.root, filters, limit=limit, offset=offset, cursor=query.get("cursor")))
        if route.startswith("/assets/"):
            name = route.removeprefix("/assets/")
            if "/" not in name and name in {"dashboard.css", "dashboard.js", "charts.js", "history.js"}:
                path = ASSETS.joinpath(name); return path.read_bytes(), CONTENT_TYPES[path.suffix]
        raise RequestError(404, "not found")
    def _serve(self, include_body: bool = True) -> None:
        route = urlsplit(self.path).path; status = 200
        if self.token and self.headers.get("Authorization") != "Bearer " + self.token:
            body, content_type, status = _json_bytes({"error": "unauthorized"})[0], CONTENT_TYPES[".json"], 401
        else:
            try: body, content_type = self._body(route)
            except RequestError as exc: body, content_type, status = _json_bytes({"error": exc.message})[0], CONTENT_TYPES[".json"], exc.status
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                status = 503 if route in ("/api/health", "/ladder.json") else 404
                body, content_type = _json_bytes({"error": str(exc)})[0], CONTENT_TYPES[".json"]
        self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0"); self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        if self.cors: self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if include_body: self.wfile.write(body)
    def do_GET(self) -> None: self._serve()
    def do_HEAD(self) -> None: self._serve(False)
    def log_message(self, fmt: str, *args: object) -> None: print(f"{self.address_string()} {fmt % args}", flush=True)
def make_server(directory: str | Path, host: str = "127.0.0.1", port: int = 18999, *, model: str | None = None,
                campaign: str | None = None, cors: bool = False, token: str | None = None) -> DashboardServer:
    root = Path(directory).expanduser().resolve(); load_board(paths_for(root, model, campaign).feed.parent)
    return DashboardServer((host, port), partial(Handler, root=root, model=model, campaign=campaign, cors=cors, token=token))
def detected_addresses(host: str, port: int) -> list[tuple[str, str]]:
    if host not in ("0.0.0.0", "::"): return [(host, "local")]
    addresses, candidates = [("127.0.0.1", "localhost")], set()
    try: candidates.update(item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None))
    except socket.gaierror: pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe: probe.connect(("198.51.100.1", 9)); candidates.add(probe.getsockname()[0])
    except OSError: pass
    for address in sorted(candidates):
        try:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
            if ip.is_loopback or ip.is_unspecified or ip.version != 4: continue
            kind = "tailnet" if ip in ipaddress.ip_network("100.64.0.0/10") else "LAN"; addresses.append((address, kind))
        except ValueError: continue
    return list(dict.fromkeys(addresses))
def serve(directory: str | Path, host: str = "127.0.0.1", port: int = 18999, **kwargs) -> None:
    server = make_server(directory, host, port, **kwargs); actual_port = int(server.server_address[1])
    print("Dashboard URLs (share only on networks you trust):", flush=True)
    for address, kind in detected_addresses(host, actual_port): print(f"  {kind:9s} http://{address}:{actual_port}/", flush=True)
    try: server.serve_forever()
    finally: server.server_close()
