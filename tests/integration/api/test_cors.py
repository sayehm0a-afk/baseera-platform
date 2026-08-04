"""CORS is configured at import time from CORS_ALLOWED_ORIGINS (main.py)
-- by the time the rest of this test session's `main` module is
imported, that env var's value is already baked into app.user_middleware.
Testing both "unset" and "set" therefore each need their own fresh
Python process (subprocess), not a reload of the already-imported
`main` module in-process.
"""

import subprocess
import sys


def _run(env_extra: dict) -> str:
    script = (
        "import main; "
        "from fastapi.middleware.cors import CORSMiddleware; "
        "present = any(m.cls is CORSMiddleware for m in main.app.user_middleware); "
        "print('CORS_PRESENT=' + str(present))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=".",
        env=env_extra,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_cors_disabled_by_default(monkeypatch):
    import os

    env = dict(os.environ)
    env.pop("CORS_ALLOWED_ORIGINS", None)
    output = _run(env)
    assert "CORS_PRESENT=False" in output


def test_cors_enabled_when_origins_configured():
    import os

    env = dict(os.environ)
    env["CORS_ALLOWED_ORIGINS"] = "http://localhost:3000"
    output = _run(env)
    assert "CORS_PRESENT=True" in output


def test_cors_exposes_the_csrf_token_response_header():
    """A cross-origin frontend (Railway subdomains, or any deployment
    where frontend/backend aren't the same site) can't read
    document.cookie for the backend's own csrf_token cookie -- login/
    refresh/me echo it back as an X-CSRF-Token response header instead
    (src/api/routes/auth.py). Without expose_headers here, CORS hides
    that header from the frontend's own fetch() calls even though it's
    present on the wire."""
    import os

    env = dict(os.environ)
    env["CORS_ALLOWED_ORIGINS"] = "http://localhost:3000"
    script = (
        "import main; "
        "from fastapi.middleware.cors import CORSMiddleware; "
        "m = next(m for m in main.app.user_middleware if m.cls is CORSMiddleware); "
        "print('EXPOSE_HEADERS=' + str(m.kwargs.get('expose_headers')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=".",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "EXPOSE_HEADERS=['X-CSRF-Token']" in result.stdout
