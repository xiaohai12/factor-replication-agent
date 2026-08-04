"""Tests for `EvidenceStore.save_run`'s artifact-bundle persistence (Phase
A1.6, docs/multi-config-evidence-plan.md): copying named file artifacts plus
the run's own return/signal series into the evidence root, atomically, with
per-artifact `artifact_sha256` recorded, and the persisted `RunRecord`'s path
fields rewritten to the evidence-root-local copies.
"""

from __future__ import annotations

import json

from src.infra.evidence import EvidenceStore
from src.infra.models.run_record import RunMetrics, RunRecord


def _run(**overrides) -> RunRecord:
    defaults = dict(
        run_id="r1", factor_id="f1", plugin_id="p1", track="original_method",
        metrics=RunMetrics(), status="success",
    )
    defaults.update(overrides)
    return RunRecord(**defaults)


class TestSaveRunBasic:
    def test_save_and_load_round_trips_metadata(self, tmp_path):
        store = EvidenceStore(base_path=str(tmp_path))
        store.save_run(_run())
        loaded = store.load_run("f1", "r1")
        assert loaded is not None
        assert loaded.run_id == "r1"

    def test_metadata_json_exists_on_disk(self, tmp_path):
        store = EvidenceStore(base_path=str(tmp_path))
        store.save_run(_run())
        assert (tmp_path / "f1" / "r1" / "metadata.json").exists()


class TestArtifactCopying:
    def test_named_artifacts_are_copied_and_hashed(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        config_src = src_dir / "config.json"
        config_src.write_text('{"weighting_rule": "vw"}')

        store = EvidenceStore(base_path=str(tmp_path / "evidence"))
        store.save_run(_run(), artifacts={"config.json": str(config_src)})

        dest = tmp_path / "evidence" / "f1" / "r1" / "config.json"
        assert dest.exists()
        assert dest.read_text() == config_src.read_text()

        meta = json.loads((tmp_path / "evidence" / "f1" / "r1" / "metadata.json").read_text())
        assert any("artifact_sha256" in log for log in meta["logs"])

    def test_missing_artifact_source_is_silently_skipped(self, tmp_path):
        store = EvidenceStore(base_path=str(tmp_path))
        # Should not raise even though the source file doesn't exist.
        store.save_run(_run(), artifacts={"config.json": str(tmp_path / "does_not_exist.json")})
        assert not (tmp_path / "f1" / "r1" / "config.json").exists()

    def test_return_and_signal_series_are_copied_and_paths_rewritten(self, tmp_path):
        transient_dir = tmp_path / "transient_scripts"
        transient_dir.mkdir()
        return_src = transient_dir / "original_method.csv"
        signal_src = transient_dir / "original_method.signal.parquet"
        return_src.write_text("permno,yyyymm,ls_return\n1,200001,0.01\n")
        signal_src.write_bytes(b"fake parquet bytes")

        store = EvidenceStore(base_path=str(tmp_path / "evidence"))
        run = _run(return_series_path=str(return_src), signal_series_path=str(signal_src))
        store.save_run(run)

        loaded = store.load_run("f1", "r1")
        assert loaded.return_series_path.endswith("return_series.csv")
        assert loaded.signal_series_path.endswith("signal_series.parquet")
        assert (tmp_path / "evidence" / "f1" / "r1" / "return_series.csv").exists()
        assert (tmp_path / "evidence" / "f1" / "r1" / "signal_series.parquet").exists()

        # The ORIGINAL RunRecord passed in must be untouched (save_run copies
        # before mutating) -- callers may still be holding/using it.
        assert run.return_series_path == str(return_src)


class TestAtomicWrite:
    def test_no_stale_staging_directory_left_behind(self, tmp_path):
        store = EvidenceStore(base_path=str(tmp_path))
        store.save_run(_run())
        assert not (tmp_path / "f1" / "r1.staging").exists()

    def test_resaving_the_same_run_id_replaces_cleanly(self, tmp_path):
        store = EvidenceStore(base_path=str(tmp_path))
        store.save_run(_run(status="failed"))
        store.save_run(_run(status="success"))
        loaded = store.load_run("f1", "r1")
        assert loaded.status == "success"
        assert not (tmp_path / "f1" / "r1.staging").exists()
