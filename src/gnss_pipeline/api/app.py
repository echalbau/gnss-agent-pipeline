"""FastAPI app: drag-and-drop upload, background processing, status polling, PDF download."""

from __future__ import annotations

import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import __version__
from ..config import available_modes, load_settings
from ..pipeline import new_job_dir, run_pipeline

STATIC = Path(__file__).parent / "static"
NEXT_STAGE = {
    "inspect_rinex": "download_products",
    "download_products": "run_engine",
    "run_engine": "evaluate_precision",
}


def _next_stage(node: str, delta: dict[str, Any]) -> str | None:
    """Mirror the graph routing so the UI knows which node runs next."""
    if node == "evaluate_precision":
        retry = delta.get("evaluation", {}).get("decision") == "retry"
        return "run_engine" if retry else "generate_report"
    ok = {
        "inspect_rinex": lambda: delta.get("qc", {}).get("passed"),
        "download_products": lambda: delta.get("products", {}).get("complete"),
        "run_engine": lambda: not delta.get("solution", {}).get("error"),
    }.get(node)
    if ok is None:
        return None
    return NEXT_STAGE[node] if ok() else "raise_alert"

app = FastAPI(title="GNSS Agent Pipeline", version=__version__)
_executor = ThreadPoolExecutor(max_workers=int(os.getenv("GNSS_WORKERS", "2")))
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _update(job_id: str, **fields: Any) -> None:
    with _lock:
        _jobs[job_id].update(fields)


def _run(job_id: str, paths: dict[str, Path], mode: str, job_dir: Path) -> None:
    def on_stage(node: str, delta: dict[str, Any]) -> None:
        with _lock:
            job = _jobs[job_id]
            if node == "raise_alert":
                job["failed_stage"] = job["completed"][-1] if job["completed"] else None
            job["completed"].append(node)
            job["stage"] = _next_stage(node, delta)
            job["attempt"] = delta.get("attempt", job["attempt"])
            job["alerts"] = delta.get("alerts", job["alerts"])

    try:
        final = run_pipeline(paths["obs"], nav=paths.get("nav"), base=paths.get("base"),
                             mode=mode, job_dir=job_dir, on_stage=on_stage)
        _update(job_id, status=final.get("status", "failed"), stage=None,
                coordinates=final.get("coordinates"), summary=final.get("summary"),
                alerts=final.get("alerts", []), report_pdf=final.get("report_pdf"))
    except Exception as exc:
        with _lock:
            _jobs[job_id].update(status="failed", stage=None,
                                 failed_stage=_jobs[job_id]["stage"])
            _jobs[job_id]["alerts"].append(f"Internal error: {type(exc).__name__}: {exc}")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/modes")
def modes() -> dict[str, Any]:
    s = load_settings()
    return {"modes": available_modes(s), "default": s["engine"]["default_mode"]}


@app.post("/api/jobs", status_code=202)
async def create_job(obs: UploadFile = File(...), nav: UploadFile | None = File(None),
                     base: UploadFile | None = File(None),
                     mode: str | None = Form(None)) -> dict[str, str]:
    settings = load_settings()
    mode = mode or settings["engine"]["default_mode"]
    if mode not in available_modes(settings):
        raise HTTPException(422, f"Unknown mode '{mode}'")

    job_dir = new_job_dir(settings)
    job_id = job_dir.name
    inp = job_dir / "input"
    inp.mkdir()
    paths: dict[str, Path] = {}
    for key, upload in (("obs", obs), ("nav", nav), ("base", base)):
        if upload is None or not upload.filename:
            continue
        dest = inp / Path(upload.filename).name
        with open(dest, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        paths[key] = dest

    with _lock:
        _jobs[job_id] = {"job_id": job_id, "status": "running", "mode": mode,
                         "stage": "inspect_rinex", "completed": [], "failed_stage": None,
                         "attempt": 0,
                         "alerts": [], "coordinates": None, "summary": None,
                         "report_pdf": None}
    _executor.submit(_run, job_id, paths, mode, job_dir)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, Any]:
    with _lock:
        job = dict(_jobs.get(job_id) or {})
    if not job:
        raise HTTPException(404, "Unknown job")
    job["report_url"] = f"/api/jobs/{job_id}/report" if job.pop("report_pdf", None) else None
    return job


@app.get("/api/jobs/{job_id}/report")
def job_report(job_id: str) -> FileResponse:
    with _lock:
        pdf = (_jobs.get(job_id) or {}).get("report_pdf")
    if not pdf or not Path(pdf).exists():
        raise HTTPException(404, "Report not available")
    return FileResponse(pdf, media_type="application/pdf", filename=f"{job_id}_report.pdf")
