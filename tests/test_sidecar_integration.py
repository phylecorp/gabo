"""Smoke tests for the packaged SAT API sidecar binary.

These tests spawn the PyInstaller-built sat-api binary and verify it starts
correctly and serves the /api/health endpoint. They are marked @integration
and skipped unless the binary has been built at the expected path.

Run only when the binary is present:
    python -m pytest tests/test_sidecar_integration.py -v -m integration

Build the binary first (from repo root):
    pyinstaller desktop/sat-api.spec \\
        --distpath desktop/pyinstaller/dist \\
        --workpath desktop/pyinstaller/build

@decision DEC-BUILD-006
@title Sidecar smoke tests run against real binary, not mocked subprocess
@status accepted
@rationale The purpose of these tests is to verify that the PyInstaller bundle
starts and serves HTTP traffic correctly. Mocking subprocess.Popen would test
nothing about the binary. The tests are skipped when the binary isn't present,
so they never block CI on machines that haven't run the build step. On machines
where the binary exists (e.g. after a local build or in a build-and-test CI stage),
the tests run for real.
"""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

# ---------------------------------------------------------------------------
# Binary location
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent
SIDECAR_BINARY = _REPO_ROOT / "desktop" / "pyinstaller" / "dist" / "sat-api" / "sat-api"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_free_port() -> int:
    """Bind to port 0, let the OS choose a free port, then return it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_http(url: str, *, timeout: float = 15.0, interval: float = 0.25) -> bool:
    """Poll url until it returns any HTTP response or timeout expires.

    Returns True if the server responded before the deadline, False otherwise.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(url, timeout=1.0)
            return True
        except httpx.TransportError:
            time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not SIDECAR_BINARY.exists(),
    reason=f"Sidecar binary not built — expected at {SIDECAR_BINARY}",
)
class TestSidecarIntegration:
    """Smoke tests that spawn the real sat-api binary and verify HTTP behaviour.

    Each test method gets its own process to ensure test isolation. The process
    is killed in the fixture teardown regardless of test outcome.
    """

    @pytest.fixture()
    def running_sidecar(self):
        """Start the sidecar on a free port; yield (proc, base_url); kill on teardown."""
        port = _find_free_port()
        proc = subprocess.Popen(
            [str(SIDECAR_BINARY), "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        base_url = f"http://127.0.0.1:{port}"
        started = _wait_for_http(f"{base_url}/api/health", timeout=20.0)
        if not started:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=5)
            pytest.fail(
                f"Sidecar did not respond within 20s on port {port}.\n"
                f"stdout: {stdout.decode(errors='replace')}\n"
                f"stderr: {stderr.decode(errors='replace')}"
            )
        yield proc, base_url
        proc.kill()
        proc.wait(timeout=10)

    def test_health_endpoint_returns_200(self, running_sidecar):
        """Spawn the sidecar binary and verify /api/health responds with HTTP 200."""
        _proc, base_url = running_sidecar
        response = httpx.get(f"{base_url}/api/health", timeout=5.0)
        assert response.status_code == 200, (
            f"Expected 200 from /api/health, got {response.status_code}. "
            f"Body: {response.text[:200]}"
        )

    def test_health_endpoint_returns_json(self, running_sidecar):
        """Health endpoint must return a JSON body (not HTML or plain text)."""
        _proc, base_url = running_sidecar
        response = httpx.get(f"{base_url}/api/health", timeout=5.0)
        assert response.status_code == 200
        data = response.json()  # raises if body is not JSON
        assert isinstance(data, dict), f"Expected dict, got {type(data)}: {data}"

    def test_binary_exits_cleanly_after_sigterm(self, running_sidecar):
        """The sidecar process must exit within 5 seconds of receiving SIGTERM."""
        proc, base_url = running_sidecar
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("Sidecar did not exit within 5s after SIGTERM")
