"""本地健康检查：确认主要模块可导入且无缺失运行时依赖。"""

import importlib

MODULES = (
    "agent",
    "backtest",
    "contracts",
    "episode_study",
    "episodes",
    "evidence_gates",
    "formal_v2",
    "margin",
    "plugins",
    "protocol_v2",
    "regime",
    "stress",
    "tradability",
    "web",
)


def run_doctor() -> dict:
    checks = []
    ok = True
    for module in MODULES:
        try:
            importlib.import_module(f"goratio.{module}")
            status = "ok"
        except Exception as exc:  # noqa: BLE001
            status = f"error: {exc}"
            ok = False
        checks.append({"module": module, "status": status})
    return {
        "schema_version": "goratio-doctor-v1",
        "ok": ok,
        "module_count": len(checks),
        "checks": checks,
    }
