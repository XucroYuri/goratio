import unittest

from goratio.web import render_dashboard_html


class WebTests(unittest.TestCase):
    def test_render_dashboard_html_is_self_contained(self) -> None:
        html = render_dashboard_html(
            {
                "source_id": "cn_public",
                "as_of": "2024-01-02",
                "ratio": {"as_of": "2024-01-02", "ratio": 23.75},
                "series": [
                    {"date": "2024-01-02", "ratio": 23.0},
                    {"date": "2024-01-03", "ratio": 23.75},
                ],
                "factor": {
                    "available": True,
                    "factors": {
                        "F1_valuation": {"percentile": 0.3, "zone": "middle"}
                    },
                },
                "evidence": {
                    "horizons": {
                        "63": {"evidence_status": "insufficient_data"}
                    }
                },
                "risk_flags": ["structural_instability"],
            }
        )

        self.assertIn("<!doctype html>", html)
        self.assertIn("只读研究工作台", html)
        self.assertIn("23.75", html)
        self.assertIn("<svg", html)
        self.assertIn("polyline", html)
        self.assertIn("structural_instability", html)
        self.assertIn("不构成投资建议", html)



import threading
import urllib.request

from goratio.web import make_dashboard_server


class WebServerTests(unittest.TestCase):
    def test_readonly_server_serves_dashboard_on_localhost(self) -> None:
        payload = {
            "source_id": "cn_public",
            "ratio": {"as_of": "2024-01-02", "ratio": 23.75},
            "factor": {"available": False},
            "evidence": {"horizons": {}},
            "risk_flags": [],
        }
        server = make_dashboard_server(payload, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/", timeout=3
            ) as response:
                body = response.read().decode("utf-8")
            self.assertIn("只读研究工作台", body)
            self.assertIn('http-equiv="refresh"', body)
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health", timeout=3
            ) as response:
                self.assertEqual(response.status, 200)
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()


    def test_readonly_server_supports_payload_factory(self) -> None:
        from goratio.web import make_dashboard_server

        calls = {"n": 0}

        def factory():
            calls["n"] += 1
            return {
                "source_id": "cn_public",
                "ratio": {"as_of": "2024-01-02", "ratio": float(calls["n"])},
                "factor": {"available": False},
                "evidence": {"horizons": {}},
                "risk_flags": [],
            }

        server = make_dashboard_server(payload_factory=factory, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/", timeout=3
            ) as response:
                body1 = response.read().decode("utf-8")
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/", timeout=3
            ) as response:
                body2 = response.read().decode("utf-8")
            self.assertIn("1.0", body1)
            self.assertIn("2.0", body2)
            self.assertGreaterEqual(calls["n"], 2)
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()


if __name__ == "__main__":
    unittest.main()