import os
import signal
import socket
import subprocess
import sys
import time

import pytest
from playwright.sync_api import expect

os.environ["no_proxy"] = "127.0.0.1,localhost"
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE_DIR = os.path.join(REPO_ROOT, "examples", "fastapi")
PORT = int(os.environ.get("POLYADMIN_TEST_PORT", "3100"))
ADMIN_URL = f"http://127.0.0.1:{PORT}/admin"
SESSION_SECRET = "browsertests-fixed-secret"

SUPERUSER = ("admin@example.com", "polyadmin")
VIEWER = ("viewer@example.com", "polyadmin")
AMELIE = ("amelie@example.com", "polyadmin")


def _port_is_free():
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", PORT)) != 0


def _wait_until_listening(timeout=120):
    """Poll the socket rather than fetching a URL: an HTTP probe cannot
    tell the app's own response from a proxy's, and accepting any status
    let the fixture yield before the server existed."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _port_is_free():
            return
        time.sleep(0.5)
    raise RuntimeError(f"nothing began listening on port {PORT}")


def _example_python():
    candidates = [
        os.path.join(EXAMPLE_DIR, ".venv", "bin", "python"),
        os.path.join(REPO_ROOT, ".venv", "bin", "python"),
        sys.executable,
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            probe = subprocess.run(
                [candidate, "-c", "import uvicorn"], capture_output=True, check=False
            )
            if probe.returncode == 0:
                return candidate
    return None


@pytest.fixture(scope="session")
def app_server():
    python = _example_python()
    if python is None:
        pytest.skip("no interpreter with uvicorn available for the example app")
    if not _port_is_free():
        pytest.fail(f"port {PORT} is already in use; stop whatever is on it")

    # start_new_session so the whole process group can be signalled:
    # uvicorn's workers are children that would keep holding the port.
    process = subprocess.Popen(
        [python, "-m", "uvicorn", "main:app", "--port", str(PORT)],
        cwd=EXAMPLE_DIR,
        env={
            **os.environ,
            "ADMIN_SESSION_SECRET": SESSION_SECRET,
            "POLYADMIN_PSEUDO_LOCALE": "1",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        _wait_until_listening()
        yield ADMIN_URL
    finally:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 1440, "height": 900}}


def _sign_in(page, credentials):
    email, password = credentials
    page.goto(f"{ADMIN_URL}/login")
    page.fill("#login-identifier", email)
    page.fill("#login-password", password)
    page.click("form:has(#login-identifier) button[type=submit]")
    # A failed sign-in leaves the form up, which would make every
    # assertion after it vacuous.
    expect(page).not_to_have_url("**/login**")


@pytest.fixture
def admin_page(page, app_server):
    _sign_in(page, SUPERUSER)
    return page


@pytest.fixture
def viewer_page(page, app_server):
    _sign_in(page, VIEWER)
    return page


@pytest.fixture
def anon_page(page, app_server):
    return page


@pytest.fixture
def amelie_page(page, app_server):
    _sign_in(page, AMELIE)
    return page
