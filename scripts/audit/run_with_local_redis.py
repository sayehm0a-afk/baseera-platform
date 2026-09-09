"""Run tests with an owned, ephemeral Redis process on localhost only.

No installation or remote connection. Refuses an occupied port; persistence
is disabled. Pass a redis-server executable, then pytest arguments after --.
"""

import argparse
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import redis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redis-server", required=True)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    with socket.socket() as check:
        try:
            check.bind(("127.0.0.1", 6379))
        except OSError:
            parser.error("Port 6379 is occupied; refusing to use or stop another Redis instance.")
    tests = args.pytest_args
    if tests and tests[0] == "--":
        tests = tests[1:]
    with tempfile.TemporaryDirectory(prefix="basirah-test-redis-") as directory:
        with (Path(directory) / "redis.log").open("w") as log:
            process = subprocess.Popen([
                args.redis_server, "--bind", "127.0.0.1", "--port", "6379",
                "--save", "", "--appendonly", "no", "--dir", directory,
            ], stdout=log, stderr=subprocess.STDOUT)
            try:
                client = redis.Redis(host="127.0.0.1", port=6379, socket_connect_timeout=0.2)
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Owned Redis failed to start.")
                    try:
                        if client.ping():
                            break
                    except redis.ConnectionError:
                        time.sleep(0.05)
                else:
                    raise RuntimeError("Owned Redis did not become ready.")
                print("Owned local Redis version:", client.info("server")["redis_version"], flush=True)
                return subprocess.call([sys.executable, "-m", "pytest", *tests])
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    sys.exit(main())
