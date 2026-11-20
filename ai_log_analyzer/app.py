from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

try:
    # 从工作区根目录启动：uvicorn ai_log_analyzer.app:app
    from .ai_client import AIConfig, analyze_with_ai
    from .analyzer import analyze_log
    from .code_investigator import investigate_with_ai
    from .code_context import (
        CodeContextError,
        configured_projects,
        get_project,
    )
except ImportError:
    # 进入本目录启动：uvicorn app:app
    from ai_client import AIConfig, analyze_with_ai
    from analyzer import analyze_log
    from code_investigator import investigate_with_ai
    from code_context import (
        CodeContextError,
        configured_projects,
        get_project,
    )


BASE_DIR = Path(__file__).resolve().parent
MAX_LOG_BYTES = 1_000_000


class AnalyzeRequest(BaseModel):
    """日志分析请求。额外字段被拒绝，避免客户端误传敏感参数。"""

    model_config = ConfigDict(extra="forbid")

    log: str = Field(default="", description="需要分析的原始日志")
    use_ai: bool = Field(default=False, description="是否调用已配置的 AI 服务进行深度分析")
    code_project_id: str | None = Field(default=None, description="需要关联分析的允许代码库 ID")


def error_response(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


def create_app() -> FastAPI:
    application = FastAPI(
        title="TraceLens API",
        description="本地优先的 AI 日志报错分析接口",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    application.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=BASE_DIR / "templates")

    @application.get("/", include_in_schema=False)
    async def index(request: Request):
        return templates.TemplateResponse(request=request, name="index.html", context={})

    @application.get("/api/status", tags=["system"])
    async def status() -> dict[str, object]:
        config = AIConfig.from_env()
        return {
            "ok": True,
            "ai_configured": config.configured,
            "model": config.model if config.configured else None,
            "max_log_bytes": MAX_LOG_BYTES,
        }

    @application.get("/api/code-projects", tags=["system"])
    async def code_projects() -> dict[str, object]:
        projects = configured_projects()
        return {
            "enabled": bool(projects),
            "projects": [project.public_dict() for project in projects],
        }

    @application.post("/api/analyze", tags=["analysis"])
    async def analyze(payload: AnalyzeRequest):
        if not payload.log.strip():
            return error_response("请粘贴或上传日志后再分析", 400)
        if len(payload.log.encode("utf-8")) > MAX_LOG_BYTES:
            return error_response("日志不能超过 1 MB，请截取错误前后的关键片段", 413)

        try:
            report = await run_in_threadpool(analyze_log, payload.log)
        except ValueError as exc:
            return error_response(str(exc), 400)

        project = None
        if payload.code_project_id:
            if not payload.use_ai:
                return error_response("关联本地代码需要同时启用 AI 深度分析", 400)
            try:
                project = get_project(payload.code_project_id)
            except CodeContextError as exc:
                return error_response(str(exc), 400)

        if payload.use_ai:
            try:
                if project:
                    ai_analysis, investigation = await run_in_threadpool(
                        investigate_with_ai,
                        report["sanitized_log"],
                        report,
                        project,
                    )
                    report["ai_analysis"] = ai_analysis
                    report["code_context"] = investigation
                    report["analysis_mode"] = "ai+investigation+local"
                else:
                    report["ai_analysis"] = await run_in_threadpool(
                        analyze_with_ai,
                        report["sanitized_log"],
                        report,
                    )
                    report["analysis_mode"] = "ai+local"
            except (RuntimeError, ValueError) as exc:
                report["ai_error"] = str(exc)

        # 脱敏后的完整日志仅供服务端 AI 分析使用，不回传浏览器。
        report.pop("sanitized_log", None)
        return report

    return application


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "5000")),
        reload=os.getenv("APP_RELOAD") == "1",
    )

