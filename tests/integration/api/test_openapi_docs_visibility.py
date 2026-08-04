"""Phase 2 Foundation Cleanup, goal 2: public /docs, /redoc, and
/openapi.json enumerate the entire route schema -- including the full
admin/owner surface -- with no auth in front of them (audit finding).
main.py now disables all three whenever BASEERA_ENV=production.

docs_url/redoc_url/openapi_url are FastAPI(...) constructor arguments,
baked into `main.app` at import time from `settings.environment` --
same reasoning as test_cors.py: testing both "development" (docs on)
and "production" (docs off) needs a fresh Python process per case, not
a reload of the already-imported `main` module in-process.
"""

import os
import subprocess
import sys


def _docs_urls_for(env_extra: dict) -> str:
    script = (
        "import main; "
        "print('DOCS_URL=' + str(main.app.docs_url)); "
        "print('REDOC_URL=' + str(main.app.redoc_url)); "
        "print('OPENAPI_URL=' + str(main.app.openapi_url))"
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


def test_docs_enabled_outside_production():
    env = dict(os.environ)
    env["BASEERA_ENV"] = "development"
    output = _docs_urls_for(env)
    assert "DOCS_URL=/docs" in output
    assert "REDOC_URL=/redoc" in output
    assert "OPENAPI_URL=/openapi.json" in output


def _production_env() -> dict:
    # BASEERA_ENV=production also requires a real SECRET_KEY and
    # DATABASE_URL (Settings._reject_insecure_secret_in_production /
    # _reject_default_database_url_in_production) -- same values
    # test_settings.py uses to exercise this combination.
    env = dict(os.environ)
    env["BASEERA_ENV"] = "production"
    env["SECRET_KEY"] = "a-real-unique-production-secret"
    env["DATABASE_URL"] = "postgresql://real_user:real_pass@prod-db.example.com:5432/basirah_prod"
    return env


def test_docs_disabled_in_production():
    output = _docs_urls_for(_production_env())
    assert "DOCS_URL=None" in output
    assert "REDOC_URL=None" in output
    assert "OPENAPI_URL=None" in output


def test_docs_routes_actually_404_in_production():
    """The constructor args above are the mechanism; this proves the
    observable effect -- a real request to each path is unroutable,
    not merely absent from app.docs_url."""
    script = (
        "import main; "
        "from fastapi.testclient import TestClient; "
        "client = TestClient(main.app); "
        "print('DOCS=' + str(client.get('/docs').status_code)); "
        "print('REDOC=' + str(client.get('/redoc').status_code)); "
        "print('OPENAPI=' + str(client.get('/openapi.json').status_code))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=".", env=_production_env(), timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert "DOCS=404" in result.stdout
    assert "REDOC=404" in result.stdout
    assert "OPENAPI=404" in result.stdout
