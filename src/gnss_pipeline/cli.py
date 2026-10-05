"""Command line interface: gnss-pipeline {run,qc,serve}."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import available_modes, load_settings


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    p = argparse.ArgumentParser(prog="gnss-pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="process a RINEX observation file")
    run.add_argument("obs")
    run.add_argument("--nav")
    run.add_argument("--base", help="base station RINEX (RTK modes)")
    run.add_argument("--mode", choices=available_modes(settings),
                     default=settings["engine"]["default_mode"])
    run.add_argument("--job-dir")

    qc = sub.add_parser("qc", help="RINEX QA/QC only")
    qc.add_argument("obs")
    qc.add_argument("--single-freq", action="store_true")

    serve = sub.add_parser("serve", help="start the web UI / API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.cmd == "qc":
        from .tools.rinex import quality_check

        report = quality_check(args.obs, settings["rinex_qc"], not args.single_freq)
        print(json.dumps(report, indent=2, default=str))
        return 0 if report["passed"] else 1

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("gnss_pipeline.api.app:app", host=args.host, port=args.port)
        return 0

    from .pipeline import run_pipeline

    final = run_pipeline(args.obs, nav=args.nav, base=args.base, mode=args.mode,
                         job_dir=args.job_dir, settings=settings,
                         on_stage=lambda node, _: logging.info("node done: %s", node))
    print(json.dumps({k: final.get(k) for k in
                      ("status", "coordinates", "summary", "report_pdf", "attempt", "alerts")},
                     indent=2, default=str))
    return 0 if final.get("status", "").startswith("completed") else 1


if __name__ == "__main__":
    sys.exit(main())
