"""Tests for `src.infra.hashing` (Phase A1.3, docs/multi-config-evidence-plan.md):
`artifact_sha256` (raw file-byte integrity) vs `series_semantic_hash`
(canonicalized content equality) are deliberately different hash kinds --
these tests lock in why they must never be conflated.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.infra.hashing import artifact_sha256, series_semantic_hash, snapshot_manifest_hash


class TestArtifactSha256:
    def test_identical_bytes_hash_equal(self, tmp_path):
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"hello world")
        f2.write_bytes(b"hello world")
        assert artifact_sha256(f1) == artifact_sha256(f2)

    def test_different_bytes_hash_differently(self, tmp_path):
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"hello world")
        f2.write_bytes(b"hello there")
        assert artifact_sha256(f1) != artifact_sha256(f2)


class TestSeriesSemanticHash:
    def _panel(self, rows):
        return pd.DataFrame(rows, columns=["permno", "yyyymm", "signal"])

    def test_identical_content_hashes_equal(self):
        rows = [(1, 200001, 0.5), (2, 200001, 0.25)]
        df1 = self._panel(rows)
        df2 = self._panel(rows)
        assert series_semantic_hash(df1, ["permno", "yyyymm"], ["signal"]) == \
            series_semantic_hash(df2, ["permno", "yyyymm"], ["signal"])

    def test_row_order_does_not_affect_hash(self):
        rows = [(1, 200001, 0.5), (2, 200001, 0.25)]
        df1 = self._panel(rows)
        df2 = self._panel(list(reversed(rows)))
        assert series_semantic_hash(df1, ["permno", "yyyymm"], ["signal"]) == \
            series_semantic_hash(df2, ["permno", "yyyymm"], ["signal"])

    def test_extra_incidental_column_does_not_affect_hash(self):
        df1 = self._panel([(1, 200001, 0.5)])
        df2 = df1.copy()
        df2["extra_col"] = "noise"
        assert series_semantic_hash(df1, ["permno", "yyyymm"], ["signal"]) == \
            series_semantic_hash(df2, ["permno", "yyyymm"], ["signal"])

    def test_float_representation_noise_does_not_affect_hash(self):
        df1 = self._panel([(1, 200001, 0.1 + 0.2)])  # 0.30000000000000004
        df2 = self._panel([(1, 200001, 0.3)])
        assert series_semantic_hash(df1, ["permno", "yyyymm"], ["signal"]) == \
            series_semantic_hash(df2, ["permno", "yyyymm"], ["signal"])

    def test_different_values_hash_differently(self):
        df1 = self._panel([(1, 200001, 0.5)])
        df2 = self._panel([(1, 200001, 0.6)])
        assert series_semantic_hash(df1, ["permno", "yyyymm"], ["signal"]) != \
            series_semantic_hash(df2, ["permno", "yyyymm"], ["signal"])

    def test_duplicate_key_raises(self):
        df = self._panel([(1, 200001, 0.5), (1, 200001, 0.6)])
        with pytest.raises(ValueError, match="duplicate key"):
            series_semantic_hash(df, ["permno", "yyyymm"], ["signal"])

    def test_missing_column_raises(self):
        df = self._panel([(1, 200001, 0.5)])
        with pytest.raises(ValueError, match="missing expected column"):
            series_semantic_hash(df, ["permno", "yyyymm"], ["not_a_column"])

    def test_nan_values_are_canonicalized(self):
        df1 = self._panel([(1, 200001, float("nan"))])
        df2 = self._panel([(1, 200001, None)])
        assert series_semantic_hash(df1, ["permno", "yyyymm"], ["signal"]) == \
            series_semantic_hash(df2, ["permno", "yyyymm"], ["signal"])


class TestSnapshotManifestHash:
    def test_none_when_storage_path_missing(self, tmp_path):
        assert snapshot_manifest_hash(tmp_path / "does_not_exist") is None

    def test_stable_for_unchanged_directory(self, tmp_path):
        (tmp_path / "crsp_msf.parquet").write_bytes(b"x" * 100)
        h1 = snapshot_manifest_hash(tmp_path)
        h2 = snapshot_manifest_hash(tmp_path)
        assert h1 == h2

    def test_changes_when_a_file_is_added(self, tmp_path):
        (tmp_path / "crsp_msf.parquet").write_bytes(b"x" * 100)
        h1 = snapshot_manifest_hash(tmp_path)
        (tmp_path / "compustat_fundamental_annual.parquet").write_bytes(b"y" * 50)
        h2 = snapshot_manifest_hash(tmp_path)
        assert h1 != h2

    def test_changes_when_a_file_size_changes(self, tmp_path):
        f = tmp_path / "crsp_msf.parquet"
        f.write_bytes(b"x" * 100)
        h1 = snapshot_manifest_hash(tmp_path)
        f.write_bytes(b"x" * 200)
        h2 = snapshot_manifest_hash(tmp_path)
        assert h1 != h2

    def test_includes_local_subdirectory(self, tmp_path):
        (tmp_path / "local").mkdir()
        (tmp_path / "local" / "CRSP_STOCK_MONTH.csv").write_bytes(b"a" * 10)
        h1 = snapshot_manifest_hash(tmp_path)
        (tmp_path / "local" / "CRSP_DELISTING.csv").write_bytes(b"b" * 10)
        h2 = snapshot_manifest_hash(tmp_path)
        assert h1 != h2
