import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from app.fetchers import fetch_cdp_browser


class TargetCreationTest(unittest.TestCase):
    def test_target_creation_uses_put_and_closes_target(self):
        requests = []
        sent = []

        class Endpoint(BaseHTTPRequestHandler):
            def do_PUT(self):
                requests.append(("PUT", self.path))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({
                    "id": "fixture-target",
                    "webSocketDebuggerUrl": "ws://127.0.0.1/fixture-target",
                }).encode())

            def do_GET(self):
                requests.append(("GET", self.path))
                self.send_response(200 if self.path.startswith("/json/close/") else 405)
                self.end_headers()
                self.wfile.write(b"Target closed")

            def log_message(self, *args):
                pass

        class Session:
            closed = False

            def send(self, message):
                sent.append(json.loads(message))

            def recv(self):
                command = sent[-1]
                result = {}
                if command["method"] == "Runtime.evaluate":
                    result = {"result": {"value": json.dumps([
                        {"title": "Local fixture", "url": "http://127.0.0.1/fixture-item"}
                    ])}}
                return json.dumps({"id": command["id"], "result": result})

            def close(self):
                self.closed = True

        server = ThreadingHTTPServer(("127.0.0.1", 0), Endpoint)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        session = Session()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch.dict(os.environ, {"CDP_URL": base}), patch(
                "app.fetchers.create_connection", return_value=session
            ):
                items = fetch_cdp_browser({"url": base + "/fixture-page", "wait_seconds": 0})
            self.assertEqual([item.title for item in items], ["Local fixture"])
            self.assertEqual(requests[0][0], "PUT")
            self.assertTrue(requests[0][1].startswith("/json/new?"))
            self.assertEqual(requests[-1], ("GET", "/json/close/fixture-target"))
            self.assertEqual(next(command["params"]["url"] for command in sent
                                  if command["method"] == "Page.navigate"), base + "/fixture-page")
            self.assertTrue(session.closed)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
