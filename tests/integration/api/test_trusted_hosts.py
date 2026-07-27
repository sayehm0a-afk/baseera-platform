"""TrustedHostMiddleware is configured at import time from TRUSTED_HOSTS
(main.py) -- same "needs a fresh Python process per env-var value"
constraint test_cors.py documents, for the same reason (already baked
into app.user_middleware by the time this test session's `main` module
is first imported).
"""

import subprocess
import sys


def _run(env_extra: dict, host_header: str) -> str:
    script = (
        "import main; "
        "from starlette.testclient import TestClient; "
        f"client = TestClient(main.app, base_url='http://{host_header}'); "
        "response = client.get('/health/live'); "
        "print('STATUS=' + str(response.status_code))"
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


def test_trusted_hosts_not_enforced_by_default(monkeypatch):
    import os

    env = dict(os.environ)
    env.pop("TRUSTED_HOSTS", None)
    output = _run(env, "anything.example.com")
    assert "STATUS=200" in output


def test_trusted_hosts_rejects_an_unlisted_host_when_configured():
    import os

    env = dict(os.environ)
    env["TRUSTED_HOSTS"] = "api.baseerah.sa"
    output = _run(env, "evil.example.com")
    assert "STATUS=400" in output


def test_trusted_hosts_accepts_a_listed_host_when_configured():
    import os

    env = dict(os.environ)
    env["TRUSTED_HOSTS"] = "api.baseerah.sa"
    output = _run(env, "api.baseerah.sa")
    assert "STATUS=200" in output
