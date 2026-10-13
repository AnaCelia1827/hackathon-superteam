import importlib.util
import json
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen


class DashboardServerTests(unittest.TestCase):
    def test_sse_session_and_abort_endpoint(self):
        path = Path(__file__).parents[2] / "dashboard" / "server.py"
        spec = importlib.util.spec_from_file_location("dashboard_server", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.session = module.Session()
        server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            start = Request(base + "/api/start", data=b'{"mode":"mock"}',
                            headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(start, timeout=5) as response:
                self.assertEqual(response.status, 202)
            with urlopen(base + "/api/events", timeout=10) as response:
                while response.readline().decode().strip() != "event: step":
                    pass
                payload = response.readline().decode().removeprefix("data: ")
                self.assertEqual(json.loads(payload)["step_index"], 0)
                abort = Request(base + "/api/abort", data=b"", method="POST")
                with urlopen(abort, timeout=5) as stopped:
                    self.assertEqual(stopped.status, 202)
            with module.session.changed:
                module.session.changed.wait_for(lambda: module.session.status != "running", timeout=5)
            state = module.session.snapshot()
            self.assertEqual(state["status"], "aborted")
            self.assertLess(len(state["events"]), 50)
            self.assertEqual(state["result"]["metrics"]["settlements"], 0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
