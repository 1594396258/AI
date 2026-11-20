from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request

from ai_client import AIConfig, analyze_with_ai
from analyzer import analyze_log


MAX_LOG_BYTES = 1_000_000


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_LOG_BYTES + 100_000

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def status():
        config = AIConfig.from_env()
        return jsonify(
            {
                "ok": True,
                "ai_configured": config.configured,
                "model": config.model if config.configured else None,
                "max_log_bytes": MAX_LOG_BYTES,
            }
        )

    @app.post("/api/analyze")
    def analyze():
        payload = request.get_json(silent=True) or {}
        log = payload.get("log", "")
        use_ai = bool(payload.get("use_ai", False))
        if not isinstance(log, str) or not log.strip():
            return jsonify({"error": "请粘贴或上传日志后再分析"}), 400
        if len(log.encode("utf-8")) > MAX_LOG_BYTES:
            return jsonify({"error": "日志不能超过 1 MB，请截取错误前后的关键片段"}), 413
        try:
            report = analyze_log(log)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if use_ai:
            try:
                report["ai_analysis"] = analyze_with_ai(report["sanitized_log"], report)
                report["analysis_mode"] = "ai+local"
            except (RuntimeError, ValueError) as exc:
                report["ai_error"] = str(exc)

        # Sanitized content is needed by the server only and should not be echoed to the browser.
        report.pop("sanitized_log", None)
        return jsonify(report)

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify({"error": "请求内容过大，日志不能超过 1 MB"}), 413

    return app


app = create_app()


if __name__ == "__main__":
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "5000"))
    app.run(host=host, port=port, debug=os.getenv("FLASK_DEBUG") == "1")

