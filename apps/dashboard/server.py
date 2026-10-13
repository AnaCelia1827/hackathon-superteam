"""Local dashboard server with streamed mock/replay sessions."""

from __future__ import annotations

import asyncio
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Condition, Event, Thread
from urllib.parse import parse_qs, urlparse

DASHBOARD = Path(__file__).resolve().parent
ROOT = DASHBOARD.parents[1]
sys.path.insert(0, str(ROOT / "apps" / "runtime"))

from looprail.agent import MarketIntelligenceAgent  # noqa: E402
from looprail.sdk import LoopRail, load_policy  # noqa: E402


class Session:
    def __init__(self) -> None:
        self.changed = Condition()
        self.stop = Event()
        self.events: list[dict] = []
        self.messages: list[tuple[str, dict]] = []
        self.budget: dict | None = None
        self.result: dict | None = None
        self.status = "idle"
        self.mode = "mock"
        self.generation = 0

    def start(self, mode: str) -> bool:
        with self.changed:
            if self.status == "running":
                return False
            self.stop = Event()
            self.events = []
            self.messages = []
            self.budget = None
            self.result = None
            self.status = "running"
            self.mode = mode
            self.generation += 1
            generation = self.generation
            self.changed.notify_all()
        Thread(target=self._run, args=(generation,), daemon=True).start()
        return True

    def _run(self, generation: int) -> None:
        try:
            policy = load_policy(ROOT / "scenarios" / "market-intelligence" / "policy.mock.json")
            rail = LoopRail(budget=policy.budget_usdc_base_units)
            result = asyncio.run(rail.run_async(
                agent=MarketIntelligenceAgent(), policy=policy,
                replay_path=(ROOT / "scenarios" / "replay" / "market-intelligence.json")
                if self.mode == "replay" else None,
                stop_event=self.stop, wall_delay_ms=120,
                event_sink=self.append,
                telemetry_sink=self.append_budget,
            )).to_dict()
            with self.changed:
                if generation == self.generation:
                    self.result = result
                    self.status = result["status"]
                    self.changed.notify_all()
        except Exception as error:
            with self.changed:
                self.result = {"error": str(error)}
                self.status = "error"
                self.changed.notify_all()

    def append(self, event: dict) -> None:
        with self.changed:
            self.events.append(event)
            self.messages.append(("step", event))
            self.changed.notify_all()

    def append_budget(self, budget: dict) -> None:
        with self.changed:
            self.budget = budget
            self.messages.append(("budget", budget))
            self.changed.notify_all()

    def snapshot(self) -> dict:
        with self.changed:
            return {
                "status": self.status, "mode": self.mode,
                "events": list(self.events), "result": self.result,
                "budget": self.budget, "message_index": len(self.messages),
            }


session = Session()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD), **kwargs)

    def _json(self, status: int, data: dict) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/state":
            self._json(200, session.snapshot())
        elif path == "/demo.mp4":
            video = ROOT / "docs" / "demo" / "looprail-demo-en.mp4"
            if not video.is_file():
                self.send_error(404, "Demo video not recorded yet")
                return
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(video.stat().st_size))
            self.end_headers()
            with video.open("rb") as source:
                self.wfile.write(source.read())
        elif path == "/api/events":
            self._stream()
        elif path.startswith("/api/"):
            self._json(404, {"error": "Unknown API route"})
        else:
            super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/start":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 1024:
                    raise ValueError("Request too large")
                mode = json.loads(self.rfile.read(length) or b"{}").get("mode", "mock")
                if mode not in {"mock", "replay"}:
                    raise ValueError("mode must be mock or replay")
            except (ValueError, json.JSONDecodeError) as error:
                self._json(400, {"error": str(error)})
                return
            self._json(202 if session.start(mode) else 409, session.snapshot())
        elif path == "/api/abort":
            session.stop.set()
            self._json(202, {"status": "abort_requested"})
        else:
            self._json(404, {"error": "Unknown API route"})

    def _stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            index = max(0, int(parse_qs(urlparse(self.path).query).get("since", ["0"])[0]))
        except ValueError:
            index = 0
        with session.changed:
            generation = session.generation
        try:
            while True:
                with session.changed:
                    session.changed.wait_for(
                        lambda: len(session.messages) > index or session.status != "running"
                        or session.generation != generation,
                        timeout=10,
                    )
                    if session.generation != generation:
                        break
                    batch = session.messages[index:]
                    index = len(session.messages)
                    status = session.status
                    result = session.result
                for kind, payload in batch:
                    self.wfile.write(f"event: {kind}\ndata: {json.dumps(payload)}\n\n".encode())
                if status != "running":
                    self.wfile.write(f"event: complete\ndata: {json.dumps(result)}\n\n".encode())
                    self.wfile.flush()
                    break
                self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == "__main__":
    print("LoopRail dashboard: http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
