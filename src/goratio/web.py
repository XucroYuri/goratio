"""只读 Web 工作台的本地 HTML 导出。

当前不做在线服务器，只把研究结果渲染为可本地打开的自包含 HTML 页面。
后续可在该 HTML 基础上加实时刷新，但不应新增任何交易下单能力。
"""

import html
import json
from typing import Mapping


def render_dashboard_html(
    payload: Mapping,
    *,
    refresh_seconds: int = None,
) -> str:
    """将结构化 payload 渲染为只读 HTML 页面。"""
    e = html.escape
    title = e("goratio 只读研究工作台")
    ratio = payload.get("ratio", {})
    factor = payload.get("factor", {})
    evidence = payload.get("evidence", {})
    risks = payload.get("risk_flags", [])

    rows = []
    if factor.get("available"):
        valuation = factor.get("valuation") or factor.get("factors", {}).get(
            "F1_valuation", {}
        )
        rows.append(
            "<tr><td>F1 估值分位</td><td>"
            + e(str(valuation.get("percentile")))
            + "</td></tr>"
        )
        if "stability" in factor:
            stability = factor["stability"]
            rows.append(
                "<tr><td>结构稳定性</td><td>"
                + e(str(stability.get("state")))
                + "</td></tr>"
            )
        if "F2_trend_confirmation" in factor.get("factors", {}):
            trend = factor["factors"]["F2_trend_confirmation"]
            rows.append(
                "<tr><td>黄金 252 日动量</td><td>"
                + e(str(trend.get("gold_252d_momentum")))
                + "</td></tr>"
            )
    if not rows:
        rows.append("<tr><td>因子状态</td><td>不可用</td></tr>")

    evidence_rows = []
    for horizon, report in evidence.get("horizons", {}).items():
        evidence_rows.append(
            "<tr><td>"
            + e(horizon)
            + "</td><td>"
            + e(str(report.get("evidence_status")))
            + "</td></tr>"
        )
    if not evidence_rows:
        evidence_rows.append("<tr><td>-</td><td>未运行</td></tr>")

    series = payload.get("series", [])
    chart_html = ""
    if len(series) >= 2:
        values = [
            float(point.get("ratio"))
            for point in series
            if point.get("ratio") is not None
        ]
        if len(values) >= 2:
            min_v = min(values)
            max_v = max(values)
            span = max(max_v - min_v, 1e-12)
            width = 640
            height = 160
            points = []
            for idx, value in enumerate(values):
                x = width * idx / (len(values) - 1)
                y = height - 8 - (height - 16) * (value - min_v) / span
                points.append(f"{x:.1f},{y:.1f}")
            chart_html = (
                "<h2>近期金油比</h2>"
                f"<svg viewBox=\"0 0 {width} {height}\" width=\"100%\" height=\"180\" role=\"img\" aria-label=\"金油比走势\">"
                f"<polyline fill=\"none\" stroke=\"#1a73e8\" stroke-width=\"1.5\" points=\"{' '.join(points)}\"/></svg>"
            )

    refresh_tag = ""
    if refresh_seconds is not None and refresh_seconds > 0:
        refresh_tag = (
            f'<meta http-equiv="refresh" content="{refresh_seconds}">'
        )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{refresh_tag}
<title>{title}</title>
<style>
body {{ font-family: sans-serif; max-width: 760px; margin: 32px auto; padding: 0 16px; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
.risk {{ color: #a33; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p>数据来源：{e(str(payload.get('source_id')))}｜数据截至：{e(str(ratio.get('as_of', payload.get('as_of', '未知'))))}</p>
<table>
<tr><th>当前比值</th><td>{e(str(ratio.get('ratio', '未知')))}</td></tr>
{''.join(rows)}
</table>
{chart_html}
<h2>v2 组合证据门槛</h2>
<table><tr><th>期限</th><th>状态</th></tr>{''.join(evidence_rows)}</table>
<h2>风险标记</h2>
<p class="risk">{e('、'.join(risks) if risks else '无')}</p>
<footer><p>仅供历史统计研究与方法复现，不构成投资建议。</p></footer>
</body>
</html>
"""


def make_dashboard_server(payload: Mapping, host: str = "127.0.0.1", port: int = 0):
    """创建只读本地 HTTP 服务（ThreadingHTTPServer）。"""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    html = render_dashboard_html(payload, refresh_seconds=60)

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html.encode("utf-8"))))
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            elif self.path == "/health":
                body = b'{"status":"ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, fmt, *args):
            return

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    return server


def serve_dashboard(payload: Mapping, host: str = "127.0.0.1", port: int = 8765) -> None:
    """运行只读本地 Web 工作台。"""
    server = make_dashboard_server(payload, host=host, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
