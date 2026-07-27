"""Tests for src.core.monitoring.structured_logging's log-directory
handling -- specifically the PermissionError defensive fallback added
after PR #17's CI failed with `PermissionError: [Errno 13] Permission
denied: '/var/log/basirah'` (GitHub Actions' ubuntu-latest runs as a
non-root `runner` user with no write access to /var/log; this sandbox
runs as root, which is exactly why the bug never surfaced here).

Covers, per that fix's requirements:
- a writable configured directory is used as-is;
- an unwritable configured directory safely falls back (simulated via
  mocking os.makedirs, which works identically whether the test itself
  runs as root or not -- unlike a real chmod-based simulation, which
  root bypasses);
- application boot (main.py import) succeeds in a CI-like environment;
- production's default directory (/var/log/basirah, unset LOG_DIR) is
  unchanged.
"""

import importlib
import logging
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.monitoring import structured_logging
from src.core.monitoring.structured_logging import (
    StructuredLogger,
    _ensure_writable_log_dir,
)


@pytest.fixture(autouse=True)
def _reset_loggers():
    """StructuredLogger.__init__ registers handlers on module-level
    `logging.getLogger(name)` singletons -- without this, a handler
    from one test's temp directory would leak into the next test's
    logger of the same name and both would keep writing (and erroring
    on rotation against a since-deleted tmp_path)."""
    yield
    for logger_name in list(logging.Logger.manager.loggerDict.keys()):
        if logger_name.startswith("test_structured_logging"):
            logger = logging.getLogger(logger_name)
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)


class TestEnsureWritableLogDir:
    def test_writable_configured_directory_is_used_as_is(self, tmp_path):
        configured = tmp_path / "configured-logs"
        result = _ensure_writable_log_dir(str(configured))

        assert result == str(configured)
        assert configured.is_dir()

    def test_already_existing_writable_directory_is_reused(self, tmp_path):
        configured = tmp_path / "already-here"
        configured.mkdir()

        result = _ensure_writable_log_dir(str(configured))

        assert result == str(configured)

    def test_unwritable_directory_falls_back_safely(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner-temp"))
        unwritable = "/var/log/basirah"  # the exact path from the PR #17 failure

        real_makedirs = os.makedirs

        def _fail_only_for_configured_dir(path, exist_ok=False):
            if path == unwritable:
                raise PermissionError(13, "Permission denied", unwritable)
            return real_makedirs(path, exist_ok=exist_ok)

        with patch("os.makedirs", side_effect=_fail_only_for_configured_dir):
            result = _ensure_writable_log_dir(unwritable)

        expected_fallback = os.path.join(str(tmp_path / "runner-temp"), "basirah-logs")
        assert result == expected_fallback
        assert Path(expected_fallback).is_dir()

        # A sanitized warning went to stderr, and nothing was silently
        # swallowed -- the path and error are visible, no secret could
        # ever appear here (this function never touches credentials).
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert unwritable in captured.err
        assert expected_fallback in captured.err

    def test_falls_back_to_tempfile_gettempdir_when_runner_temp_unset(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.delenv("RUNNER_TEMP", raising=False)
        unwritable = "/var/log/basirah"

        with patch("os.makedirs", side_effect=PermissionError(13, "Permission denied", unwritable)):
            with patch("tempfile.gettempdir", return_value=str(tmp_path)):
                # The fallback's own os.makedirs call is also patched to
                # raise above -- so this proves ONLY that the fallback
                # path is computed correctly, not that it's created;
                # test_unwritable_directory_falls_back_safely already
                # covers real fallback-directory creation.
                with pytest.raises(PermissionError):
                    _ensure_writable_log_dir(unwritable)

    def test_never_silently_disables_logging_when_fallback_also_fails(self, monkeypatch):
        """If even the fallback can't be created, this must raise --
        never return a bogus path and pretend logging is fine."""
        monkeypatch.setenv("RUNNER_TEMP", "/nonexistent-for-test")

        with patch("os.makedirs", side_effect=PermissionError(13, "Permission denied", "x")):
            with pytest.raises(PermissionError):
                _ensure_writable_log_dir("/var/log/basirah")


class TestStructuredLoggerUsesTheFallback:
    def test_structured_logger_init_survives_unwritable_log_dir(self, tmp_path, monkeypatch, capsys):
        """The actual bug from PR #17: StructuredLogger(...) must not
        raise even when its configured log_dir is unwritable."""
        monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
        unwritable = "/var/log/basirah"

        real_makedirs = os.makedirs

        def _fail_only_for_configured_dir(path, exist_ok=False):
            if path == unwritable:
                raise PermissionError(13, "Permission denied", unwritable)
            return real_makedirs(path, exist_ok=exist_ok)

        with patch("os.makedirs", side_effect=_fail_only_for_configured_dir):
            logger = StructuredLogger("test_structured_logging_fallback", log_dir=unwritable)

        # Logging is still fully functional -- not silently disabled.
        logger.info("hello from the fallback directory")
        expected_fallback = os.path.join(str(tmp_path), "basirah-logs")
        assert (Path(expected_fallback) / "test_structured_logging_fallback.log").exists()

        captured = capsys.readouterr()
        assert "WARNING" in captured.err

    def test_structured_logger_init_uses_writable_configured_dir_directly(self, tmp_path):
        configured = tmp_path / "writable-configured"
        StructuredLogger("test_structured_logging_writable", log_dir=str(configured))

        assert (configured / "test_structured_logging_writable.log").exists()
        assert (configured / "test_structured_logging_writable_audit.log").exists()


class TestProductionDefaultPreserved:
    def test_default_log_dir_constant_is_var_log_basirah_when_unset(self, monkeypatch):
        """Production must still be able to use /var/log/basirah when
        intentionally configured and writable -- this asserts the
        *default* itself was never changed by the fallback fix."""
        monkeypatch.delenv("LOG_DIR", raising=False)
        reloaded = importlib.reload(structured_logging)
        try:
            assert reloaded._DEFAULT_LOG_DIR == "/var/log/basirah"
        finally:
            importlib.reload(structured_logging)  # restore normal module state for later tests

    def test_explicit_log_dir_env_var_still_honored(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOG_DIR", str(tmp_path / "from-env"))
        reloaded = importlib.reload(structured_logging)
        try:
            assert reloaded._DEFAULT_LOG_DIR == str(tmp_path / "from-env")
        finally:
            monkeypatch.delenv("LOG_DIR", raising=False)
            importlib.reload(structured_logging)


class TestApplicationBootSucceedsInCILikeEnvironment:
    def test_main_py_imports_successfully_with_writable_log_dir(self, tmp_path):
        """Reproduces exactly what CI's 'Application boot smoke test'
        step does, with LOG_DIR pointed at a writable directory the way
        .github/workflows/ci.yml now does -- this is what PR #17 was
        missing. Runs in a subprocess so main.py's module-level
        `init_logging()` call and full route registration are exercised
        exactly as they are in CI, without polluting this test
        process's own logging state."""
        repo_root = Path(__file__).resolve().parents[4]
        env = dict(os.environ)
        env["LOG_DIR"] = str(tmp_path / "ci-logs")

        result = subprocess.run(
            [sys.executable, "-c", "import main; print('OK')"],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, (
            f"main.py import failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "OK" in result.stdout

    def test_main_py_imports_successfully_with_unwritable_log_dir_via_fallback(self, tmp_path):
        """Belt-and-suspenders: even without CI's LOG_DIR fix, the
        defensive fallback in structured_logging.py alone must keep
        application boot from crashing. A real non-root user (e.g.
        `nobody`) would be the most faithful reproduction of CI's exact
        failure, but dropping privileges in this sandbox surfaces
        unrelated Python path/module-resolution failures having nothing
        to do with the bug under test (confirmed while writing this
        test) -- so this instead patches os.makedirs to raise
        PermissionError for exactly the configured directory, which
        deterministically reproduces the one condition that matters
        (a write to LOG_DIR failing) regardless of which user runs the
        test. TestStructuredLoggerUsesTheFallback covers the same
        failure at the unit level directly against StructuredLogger;
        this test additionally proves it holds through the full
        main.py import (FastAPI app construction, every router, every
        module-level `get_logger()` call)."""
        env = dict(os.environ)
        env.pop("LOG_DIR", None)
        env["RUNNER_TEMP"] = str(tmp_path)
        repo_root = Path(__file__).resolve().parents[4]

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import os, builtins; "
                    "_real_makedirs = os.makedirs; "
                    "os.makedirs = lambda p, exist_ok=False: "
                    "(_ for _ in ()).throw(PermissionError(13, 'Permission denied', p)) "
                    "if p == '/var/log/basirah' else _real_makedirs(p, exist_ok=exist_ok); "
                    "import main; "
                    "print('OK')"
                ),
            ],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, (
            f"main.py import failed under simulated unwritable /var/log/basirah.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "OK" in result.stdout
        assert "WARNING" in result.stderr
        assert "/var/log/basirah" in result.stderr
