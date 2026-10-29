import json
import subprocess
import sys
import time
import urllib.request


def test_engine_prints_ready_line_and_serves_health() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "gamesense", "--token", "cli-token", "--log-level", "WARNING"],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        ready = json.loads(proc.stdout.readline())
        assert ready["event"] == "ready" and "token" not in ready
        req = urllib.request.Request(
            f"http://127.0.0.1:{ready['port']}/health", headers={"x-gamesense-token": "cli-token"}
        )
        for _ in range(50):
            try:
                with urllib.request.urlopen(req, timeout=1) as res:
                    assert json.load(res)["ok"] is True
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("engine never became healthy")
    finally:
        proc.terminate()
        proc.wait(timeout=10)
