from conftest import write_rinex3

from gnss_pipeline.tools.rinex import quality_check


def test_good_file_passes(tmp_path, settings):
    qc = quality_check(write_rinex3(tmp_path / "a.rnx"), settings["rinex_qc"], True)
    assert qc["passed"], qc["errors"]
    assert qc["n_epochs"] == 241
    assert abs(qc["duration_h"] - 2.0) < 1e-9
    assert qc["gap_ratio"] == 0


def test_short_session_fails(tmp_path, settings):
    qc = quality_check(write_rinex3(tmp_path / "a.rnx", hours=0.5), settings["rinex_qc"], True)
    assert not qc["passed"]
    assert any("minimum" in e for e in qc["errors"])


def test_gaps_detected(tmp_path, settings):
    qc = quality_check(write_rinex3(tmp_path / "a.rnx", gap=(50, 100)), settings["rinex_qc"], True)
    assert not qc["passed"]
    assert qc["gap_ratio"] > 0.1


def test_single_frequency_rejected_for_ppp(tmp_path, settings):
    path = write_rinex3(tmp_path / "a.rnx", dual=False)
    assert not quality_check(path, settings["rinex_qc"], True)["passed"]
    assert quality_check(path, settings["rinex_qc"], False)["passed"]


def test_garbage_is_unreadable(tmp_path, settings):
    p = tmp_path / "junk.rnx"
    p.write_text("this is not rinex\n" * 10)
    qc = quality_check(p, settings["rinex_qc"], True)
    assert not qc["passed"] and "Unreadable" in qc["errors"][0]
