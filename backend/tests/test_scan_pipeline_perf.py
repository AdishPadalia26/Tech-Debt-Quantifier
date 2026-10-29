"""Performance/regression tests for the scan pipeline (profiling, sampling)."""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from tools.path_filters import is_non_principal_path

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    """Run a git command in ``repo``."""
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env=env,
    )


@pytest.fixture()
def tiny_repo(tmp_path: Path) -> Path:
    """Create a small git repo with three commits by two authors."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    authors = [
        ("Alice", "alice@example.com", "2024-01-01T00:00:00+0000"),
        ("Bob", "bob@example.com", "2024-03-01T00:00:00+0000"),
        ("Alice", "alice@example.com", "2024-06-01T00:00:00+0000"),
    ]
    for idx, (name, email, date) in enumerate(authors):
        (repo / f"mod_{idx}.py").write_text(f"def f{idx}():\n    return {idx}\n")
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
            "GIT_COMMITTER_DATE": date,
        }
        _git(repo, "add", ".", env=env)
        _git(repo, "commit", "-q", "-m", f"commit {idx}", env=env)
    return repo


@pytest.fixture()
def no_pydriller(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any use of pydriller.Repository fail loudly."""
    try:
        import pydriller
    except ImportError:
        return

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("pydriller.Repository must not be used")

    monkeypatch.setattr(pydriller, "Repository", _boom)


def test_profiler_team_and_ai_fast_without_pydriller(
    tiny_repo: Path, no_pydriller: None
) -> None:
    """Team profiling + AI detection use git log only and finish quickly."""
    from intelligence.repo_profiler import RepoProfiler

    profiler = RepoProfiler()
    start = time.perf_counter()
    team = profiler.profile_team(str(tiny_repo))
    ai = profiler.detect_ai_generated_code(str(tiny_repo))
    elapsed = time.perf_counter() - start

    assert elapsed < 5
    assert team["total_commits"] == 3
    assert team["unique_authors"] == 2
    assert team["team_size"] == 2
    assert team["bus_factor"] == 2
    assert team["repo_age_days"] == 152
    assert team["is_solo"] is False
    for key in ("estimated_team_size", "active_contributors", "commit_frequency"):
        assert key in team

    assert ai["method"] == "disabled"
    assert ai["suspected_files"] == []
    assert ai["total_suspected"] == 0
    assert ai["total_suspected_lines"] == 0
    assert "recommendation" in ai


def test_profile_team_no_git_falls_back(tmp_path: Path) -> None:
    """A directory without .git returns the default profile."""
    from intelligence.repo_profiler import RepoProfiler

    team = RepoProfiler().profile_team(str(tmp_path))
    assert team["total_commits"] == 0
    assert team["bus_factor"] == 1


def _make_tree(root: Path) -> None:
    """Create ~300 code files across dirs and size buckets."""
    for top in ("pkg", "lib", "scripts"):
        for i in range(100):
            d = root / top
            d.mkdir(parents=True, exist_ok=True)
            size = 20_000 if i % 10 == 0 else 100
            body = "def f():\n    return 1\n" + "#" * size + "\n"
            (d / f"m{i}.py").write_text(body)
    (root / "root.py").write_text("def g():\n    return 2\n")


def test_stratified_sampling_deterministic_and_keys(tmp_path: Path) -> None:
    """Sampling is deterministic, stratified, and reports extrapolation keys."""
    from tools.static_analysis import MAX_FILES, StaticAnalyzer

    _make_tree(tmp_path)
    s1 = StaticAnalyzer().get_summary(str(tmp_path))
    analyzer2 = StaticAnalyzer()
    s2 = analyzer2.get_summary(str(tmp_path))

    for key in (
        "files_eligible",
        "files_sampled",
        "sample_ratio",
        "functions_estimated_total",
        "total_functions",
        "total_files_scanned",
    ):
        assert key in s1

    assert s1["files_eligible"] == 301
    assert s1["files_sampled"] == MAX_FILES
    assert s1["sample_ratio"] == pytest.approx(MAX_FILES / 301, abs=1e-3)
    assert s1["functions_estimated_total"] == round(
        s1["total_functions"] / (MAX_FILES / 301)
    )
    assert s1["all_functions"] == s2["all_functions"]

    sampled = analyzer2._sampled_files
    tops = {Path(os.path.relpath(p, tmp_path)).parts[0] for p in sampled}
    assert {"pkg", "lib", "scripts", "root.py"} <= tops
    big = [p for p in sampled if os.path.getsize(p) > 10_000]
    assert big, "large-file stratum must be represented"


def test_small_repo_scans_all(tmp_path: Path) -> None:
    """Repos under the cap are scanned fully with ratio 1.0."""
    from tools.static_analysis import StaticAnalyzer

    (tmp_path / "a.py").write_text("def a():\n    return 1\n")
    (tmp_path / "b.py").write_text("def b():\n    return 1\n")
    summary = StaticAnalyzer().get_summary(str(tmp_path))
    assert summary["files_eligible"] == 2
    assert summary["files_sampled"] == 2
    assert summary["sample_ratio"] == 1.0
    assert summary["functions_estimated_total"] == summary["total_functions"] == 2


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("docs_src/tutorial001.py", "docs"),
        ("tests/test_x.py", "test"),
        ("src/app.py", None),
        ("src\\pkg\\test_utils.py", "test"),
        ("web/app.spec.ts", "test"),
        ("pkg/foo_test.go", "test"),
        ("docs/conf.py", "docs"),
        ("examples/basic/main.py", "example"),
        ("demo/run.py", "example"),
        ("proto/api_pb2.py", "generated"),
        ("static/app.min.js", "generated"),
        ("ui/__generated__/types.ts", "generated"),
        ("contest.py", None),
        ("", None),
    ],
)
def test_is_non_principal_path(path: str, expected: str | None) -> None:
    """Path classification rules."""
    assert is_non_principal_path(path) == expected


def test_get_risky_files_uses_given_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passing summary= skips StaticAnalyzer.get_summary entirely."""
    from tools import static_analysis
    from tools.git_mining import GitMiner

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("get_summary must not be called")

    monkeypatch.setattr(static_analysis.StaticAnalyzer, "get_summary", _boom)

    summary = {
        "all_functions": [
            {"file": "a.py", "function": "f", "complexity": 25, "severity": "high"}
        ]
    }
    miner = GitMiner()
    monkeypatch.setattr(
        miner,
        "get_hotspots",
        lambda repo_path, max_commits=None: [
            {"file": "a.py", "change_count": 12, "unique_authors": 2, "last_changed": None}
        ],
    )
    risky = miner.get_risky_files(str(tmp_path), summary=summary)
    assert len(risky) == 1

    # Fallback path also reuses the summary.
    monkeypatch.setattr(miner, "get_hotspots", lambda repo_path, max_commits=None: [])
    risky_fb = miner.get_risky_files(str(tmp_path), summary=summary)
    assert len(risky_fb) == 1


def test_get_hotspots_all_commits(tiny_repo: Path) -> None:
    """Default get_hotspots reads all commits in the clone."""
    from tools.git_mining import GitMiner

    hotspots = GitMiner().get_hotspots(str(tiny_repo))
    assert {h["file"] for h in hotspots} == {"mod_0.py", "mod_1.py", "mod_2.py"}
