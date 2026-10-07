"""Local FastAPI upload API with self-hosted Swagger UI and serial jobs."""

import fcntl
import hmac
import os
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.core.chat import (
    ChatBusyError,
    ChatModelUnavailableError,
    ChatService,
    OllamaProtocolError,
    OllamaUnavailableError,
)
from app.core.llm import DEFAULT_MODEL, OLLAMA_BASE_URL
from app.core.research_config import CONFIG as RESEARCH_CONFIG
from app.core.service import JobService
from app.models.analysis import AnalysisPlan
from app.models.chat import ChatRequest
from app.models.dataset import SourceProfile
from app.models.job import PipelineType
from app.models.research import JobResponse

key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class NDJSONStreamingResponse(StreamingResponse):
    media_type = "application/x-ndjson"


def authorize(key: Annotated[str | None, Depends(key_header)]):
    expected = os.environ.get("LOCAL_AI_API_KEY")
    if expected and (not key or not hmac.compare_digest(key, expected)):
        raise HTTPException(401, "Invalid API key")


def create_app(storage: Path | None = None, chat_service: ChatService | None = None):
    root = storage or Path(os.environ.get("LOCAL_AI_STORAGE", "outputs/api"))
    chat_service = chat_service if chat_service is not None else ChatService()

    @asynccontextmanager
    async def lifespan(app):
        root.mkdir(parents=True, exist_ok=True)
        # Multiple Uvicorn workers would race recovery and exceed the RAM budget.
        with (root / "server.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Use one Uvicorn worker per storage directory")
            app.state.service = JobService(root)
            try:
                yield
            finally:
                app.state.service.close()

    app = FastAPI(
        title="Local LLM Data Assistant",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
        description="Upload a file, receive a job ID, poll status, then download artifacts. One heavy job runs at a time.",
    )
    app.mount(
        "/static/swagger",
        StaticFiles(directory=Path(__file__).parent / "static" / "swagger"),
        name="swagger",
    )

    @app.middleware("http")
    async def local_default(request, call_next):
        from fastapi.responses import JSONResponse

        if (
            not os.environ.get("LOCAL_AI_API_KEY")
            and request.client
            and request.client.host not in {"127.0.0.1", "::1", "testclient"}
        ):
            return JSONResponse(
                {
                    "detail": "Remote use requires LOCAL_AI_API_KEY and a private network"
                },
                status_code=403,
            )
        return await call_next(request)

    @app.get("/", include_in_schema=False)
    def index():
        return RedirectResponse("/docs")

    @app.get("/docs", include_in_schema=False)
    def docs():
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title=app.title,
            swagger_js_url="/static/swagger/swagger-ui-bundle.js?v=5.33.0",
            swagger_css_url="/static/swagger/swagger-ui.css?v=5.33.0",
            swagger_favicon_url="/static/swagger/favicon-32x32.png",
            swagger_ui_parameters={"validatorUrl": None},
        )

    @app.get("/health", dependencies=[Depends(authorize)])
    def health():
        import httpx

        try:
            with httpx.Client(timeout=3, trust_env=False) as client:
                models = (
                    client.get(f"{OLLAMA_BASE_URL}/api/tags")
                    .json()
                    .get("models", [])
                )
            available = {m.get("name") for m in models}
            qwen = DEFAULT_MODEL in available
            research_available = RESEARCH_CONFIG.model in available
        except Exception:
            qwen = False
            research_available = False
        return {
            "api": "ok",
            "qwen3_8b_available": qwen,
            "research_model": RESEARCH_CONFIG.model,
            "research_model_available": research_available,
            "Rscript": bool(shutil.which("Rscript")),
            "worker_count": 1,
        }

    def response(job):
        artifacts = {p.name: p for p in job.artifacts}
        return {
            "id": job.id,
            "pipeline": job.pipeline,
            "status": job.status,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "error": job.error,
            "artifacts": [
                {"name": p.name, "url": f"/jobs/{job.id}/artifacts/{p.name}"}
                for p in artifacts.values()
            ],
            "status_url": f"/jobs/{job.id}",
            "research": None,
        }

    async def submit(file, pipeline, suffix, options):
        name = Path((file.filename or "").replace("\\", "/")).name
        if Path(name).suffix.lower() != suffix:
            raise HTTPException(422, f"Upload a {suffix} file")
        name = re.sub(r"[^\w. -]", "_", name)[:180]
        folder = root / "uploads" / str(uuid4())
        folder.mkdir(parents=True)
        path = folder / name
        size = 0
        try:
            with path.open("xb") as target:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > 256 * 1024 * 1024:
                        raise HTTPException(413, "MVP upload limit is 256 MiB")
                    target.write(chunk)
            if not size:
                raise HTTPException(422, "Input file is empty")
            path.chmod(0o400)
            return response(app.state.service.submit(pipeline, path, options))
        finally:
            await file.close()

    @app.post(
        "/chat/stream",
        dependencies=[Depends(authorize)],
        tags=["Chat"],
        description=f"Stream a stateless response from the server's local {DEFAULT_MODEL} model as NDJSON.",
        response_class=NDJSONStreamingResponse,
        responses={
            409: {"description": "The heavy-compute resource is busy"},
            502: {"description": "Ollama returned an unexpected response"},
            503: {"description": f"Ollama or {DEFAULT_MODEL} is unavailable"},
        },
    )
    async def chat(payload: ChatRequest, request: Request):
        try:
            session = await chat_service.open(payload.messages, payload.memories)
        except ChatBusyError as exc:
            raise HTTPException(
                409, "The local AI server is busy processing another task"
            ) from exc
        except ChatModelUnavailableError as exc:
            raise HTTPException(503, f"{DEFAULT_MODEL} is unavailable") from exc
        except OllamaUnavailableError as exc:
            raise HTTPException(503, "Ollama is unavailable") from exc
        except OllamaProtocolError as exc:
            raise HTTPException(502, "Ollama returned an unexpected response") from exc

        async def stream():
            try:
                async for event in session.events():
                    if await request.is_disconnected():
                        return
                    yield event
            finally:
                await session.aclose()

        return NDJSONStreamingResponse(
            stream(),
            headers={"Cache-Control": "no-cache"},
        )

    @app.post(
        "/pipelines/flashcards",
        status_code=202,
        dependencies=[Depends(authorize)],
        tags=["Pipelines"],
    )
    async def flashcards(
        file: UploadFile,
        cards_per_chunk: Annotated[int, Form(ge=1, le=12)] = 5,
        max_chunk_chars: Annotated[int, Form(ge=500, le=4000)] = 3000,
    ):
        return await submit(
            file,
            PipelineType.FLASHCARDS,
            ".txt",
            {"cards_per_chunk": cards_per_chunk, "max_chunk_chars": max_chunk_chars},
        )

    @app.post(
        "/pipelines/research",
        status_code=202,
        dependencies=[Depends(authorize)],
        tags=["Pipelines"],
    )
    async def research(file: UploadFile):
        return await submit(file, PipelineType.RESEARCH, ".pdf", {})

    @app.post(
        "/pipelines/dataset",
        status_code=202,
        dependencies=[Depends(authorize)],
        tags=["Pipelines"],
    )
    async def dataset(
        file: UploadFile,
        date_order: Annotated[Literal["dmy", "mdy", "ymd"], Form()] = "dmy",
        trust_date_order: Annotated[bool, Form()] = False,
        record_mode: Annotated[
            Literal["single_line", "standard"], Form()
        ] = "single_line",
        analysis_plan: Annotated[
            str,
            Form(
                description='JSON, e.g. {"analyses":[{"test":"pearson","columns":["age","score"]}]}'
            ),
        ] = '{"analyses":[]}',
        interpret: Annotated[bool, Form()] = True,
        source_profile: Annotated[
            str,
            Form(
                description="Optional JSON source profile overriding date and record settings"
            ),
        ] = "",
    ):
        try:
            plan = AnalysisPlan.model_validate_json(analysis_plan)
            profile = (
                SourceProfile.model_validate_json(source_profile)
                if source_profile
                else None
            )
        except ValidationError as exc:
            raise HTTPException(422, str(exc))
        if profile:
            date_order = profile.date_order
            trust_date_order = profile.trust_date_order
            record_mode = profile.record_mode
        return await submit(
            file,
            PipelineType.DATASET,
            ".csv",
            {
                "date_order": date_order,
                "trust_date_order": trust_date_order,
                "record_mode": record_mode,
                "plan": plan.model_dump(),
                "interpret": interpret,
                "source_profile": profile.model_dump() if profile else None,
            },
        )

    @app.get("/jobs", dependencies=[Depends(authorize)], tags=["Jobs"], response_model=list[JobResponse])
    def jobs():
        return [response(j) for j in app.state.service.list()]

    @app.get("/jobs/{job_id}", dependencies=[Depends(authorize)], tags=["Jobs"], response_model=JobResponse)
    def job(job_id: UUID):
        value = app.state.service.get(job_id)
        if not value:
            raise HTTPException(404, "Unknown job")
        return response(value)

    @app.get(
        "/jobs/{job_id}/artifacts/{filename}",
        dependencies=[Depends(authorize)],
        tags=["Jobs"],
    )
    def artifact(job_id: UUID, filename: str):
        value = app.state.service.get(job_id)
        if not value:
            raise HTTPException(404, "Unknown job")
        allowed = {p.name: p for p in value.artifacts}
        for name in (
            "job.json",
            "worker.log",
            "error.txt",
            "interpretation_rejections.jsonl",
            "research_diagnostics.json",
            "research_rejections.jsonl",
            "research_source_map.json",
            "research_evidence.json",
            "research_profile.json",
            "research_coverage.json",
            "research_plan.json",
        ):
            path = value.output_dir / name
            if path.is_file():
                allowed[name] = path
        path = allowed.get(filename)
        if (
            not path
            or not path.is_file()
            or path.resolve().parent != value.output_dir.resolve()
        ):
            raise HTTPException(404, "Unknown artifact")
        return FileResponse(path, filename=filename)

    return app


app = create_app()
