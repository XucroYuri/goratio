import unittest

from goratio.web import render_dashboard_html


class WebTests(unittest.TestCase):
    def test_render_dashboard_html_is_self_contained(self) -> None:
        html = render_dashboard_html(
            {
                "source_id": "cn_public",
                "as_of": "2024-01-02",
                "ratio": {"as_of": "2024-01-02", "ratio": 23.75},
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
        self.assertIn("structural_instability", html)
        self.assertIn("不构成投资建议", html)


if __name__ == "__main__":
    unittest.main()
