"""Tests for `src.infra.provenance.collect_runtime_provenance` (Phase 0.5,
docs/multi-config-evidence-plan.md): a generated backtest script does
`from src.infra.backtest_engine import BacktestExecutor` at run time, so
"same script bytes" alone does not prove "same execution logic" -- this
records what actually executed (git commit/dirty state, engine module source
hash, interpreter/dependency versions, external FF-factor file hash).
"""

from __future__ import annotations

from src.infra.provenance import collect_runtime_provenance


class TestCollectRuntimeProvenance:
    def test_returns_all_expected_keys(self):
        prov = collect_runtime_provenance()
        assert set(prov.keys()) == {
            "git_commit", "git_dirty", "engine_source_hash",
            "python_version", "package_versions", "ff_factors_hash",
        }

    def test_git_commit_is_a_real_hash_in_this_repo_checkout(self):
        prov = collect_runtime_provenance()
        # This repo IS a git checkout, so this must resolve to a real commit,
        # not the "unknown" fallback.
        assert prov["git_commit"] != "unknown"
        assert len(prov["git_commit"]) == 40  # full SHA-1 hex

    def test_git_dirty_is_a_bool_in_this_repo_checkout(self):
        prov = collect_runtime_provenance()
        assert isinstance(prov["git_dirty"], bool)

    def test_engine_source_hash_is_a_real_sha256_and_deterministic(self):
        prov1 = collect_runtime_provenance()
        prov2 = collect_runtime_provenance()
        assert prov1["engine_source_hash"] is not None
        assert len(prov1["engine_source_hash"]) == 64  # sha256 hex digest
        assert prov1["engine_source_hash"] == prov2["engine_source_hash"]

    def test_package_versions_cover_tracked_packages(self):
        prov = collect_runtime_provenance()
        assert set(prov["package_versions"].keys()) == {
            "pandas", "numpy", "statsmodels", "linearmodels",
        }
        # pandas/numpy are hard project dependencies -- must resolve to a
        # real version string, never the "not_installed" fallback.
        assert prov["package_versions"]["pandas"] != "not_installed"
        assert prov["package_versions"]["numpy"] != "not_installed"

    def test_ff_factors_hash_none_when_not_supplied(self):
        prov = collect_runtime_provenance(ff_factors_path=None)
        assert prov["ff_factors_hash"] is None

    def test_ff_factors_hash_none_when_path_does_not_exist(self):
        prov = collect_runtime_provenance(ff_factors_path="/no/such/file.parquet")
        assert prov["ff_factors_hash"] is None

    def test_ff_factors_hash_computed_when_file_exists(self, tmp_path):
        f = tmp_path / "ff.parquet"
        f.write_bytes(b"fake parquet bytes")
        prov = collect_runtime_provenance(ff_factors_path=str(f))
        assert prov["ff_factors_hash"] is not None
        assert len(prov["ff_factors_hash"]) == 64

    def test_never_raises_even_with_bogus_input(self):
        # Should not raise regardless of a nonsense path.
        collect_runtime_provenance(ff_factors_path="\0invalid")
