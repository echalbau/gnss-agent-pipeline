from pathlib import Path

from conftest import write_pos, write_rinex3

from gnss_pipeline.nodes import igs_downloader, rtk_ppp_engine
from gnss_pipeline.pipeline import run_pipeline


def test_corrupt_rinex_ends_with_alert(tmp_path, settings):
    bad = tmp_path / "bad.rnx"
    bad.write_text("garbage\n")
    seen = []
    final = run_pipeline(bad, settings=settings, on_stage=lambda n, _: seen.append(n))
    assert seen == ["inspect_rinex", "raise_alert"]
    assert final["status"] == "failed"
    assert (Path(final["job_dir"]) / "alert.json").exists()


def test_missing_products_end_with_alert(tmp_path, settings, monkeypatch):
    monkeypatch.setattr(igs_downloader, "acquire_products", lambda s, cfg: {
        "complete": False, "missing": ["orbit"], "log": [], "solution": None})
    final = run_pipeline(write_rinex3(tmp_path / "a.rnx"), settings=settings)
    assert final["status"] == "failed"
    assert any("Missing products" in a for a in final["alerts"])


def test_retry_loop_then_report(tmp_path, settings, monkeypatch):
    monkeypatch.setattr(igs_downloader, "acquire_products", lambda s, cfg: {
        "complete": True, "missing": [], "log": [], "solution": "FIN",
        "orbit": ["o.sp3"], "clock": ["c.clk"], "atx": ["igs20.atx"]})

    calls = []

    def fake_engine(exe, conf, out_pos, inputs, timeout):
        calls.append(inputs)
        # first attempt does not converge, second does
        write_pos(Path(out_pos), sigma_end=0.3 if len(calls) == 1 else 0.005)

    monkeypatch.setattr(rtk_ppp_engine, "run_rnx2rtkp", fake_engine)
    seen = []
    final = run_pipeline(write_rinex3(tmp_path / "a.rnx"), settings=settings,
                         on_stage=lambda n, _: seen.append(n))

    assert seen == ["inspect_rinex", "download_products", "run_engine", "evaluate_precision",
                    "run_engine", "evaluate_precision", "generate_report"]
    assert final["status"] == "completed"
    assert final["attempt"] == 2
    assert final["engine_options"] == {"pos1-soltype": "combined"}  # heuristic step 1
    assert "pos1-soltype     " in Path(final["job_dir"], "attempt_02", "rnx2rtkp.conf").read_text()
    assert Path(final["report_pdf"]).stat().st_size > 1000
    assert calls[0][1:] == ["o.sp3", "c.clk"]


def test_retry_budget_exhausted_still_reports(tmp_path, settings, monkeypatch):
    settings["evaluation"]["max_attempts"] = 2
    monkeypatch.setattr(igs_downloader, "acquire_products", lambda s, cfg: {
        "complete": True, "missing": [], "log": [], "solution": "FIN",
        "orbit": ["o.sp3"], "clock": ["c.clk"], "atx": ["a.atx"]})
    monkeypatch.setattr(rtk_ppp_engine, "run_rnx2rtkp",
                        lambda exe, conf, out, inp, to: write_pos(Path(out), sigma_end=0.3))
    final = run_pipeline(write_rinex3(tmp_path / "a.rnx"), settings=settings)
    assert final["status"] == "completed_with_warnings"
    assert "WARNING" in final["summary"]
