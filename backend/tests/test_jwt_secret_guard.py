"""Регрессия: приложение не поднимается в проде с небезопасным JWT_SECRET.

Проверка выполняется на импорте backend.main, поэтому каждый случай —
отдельный процесс.
"""

import os
import subprocess
import sys

import pytest


GOOD_SECRET = "x7Kp2mQvR9dLwF4tYbN6hJ3sZ8cV5gA1nE0uT" + "qWmXyPoI"


def _run(secret, debug="false", testing="false"):
    env = {
        "JWT_SECRET": secret,
        "DEBUG": debug,
        "TESTING": testing,
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
    }
    return subprocess.run(
        [sys.executable, "-c", "import backend.main"],
        capture_output=True, text=True, env=env, timeout=300,
    )


class TestProductionRefusesWeakSecret:

    def test_placeholder_secret_refused(self):
        proc = _run("CHANGE-ME-IN-PRODUCTION")
        assert proc.returncode != 0
        assert "JWT_SECRET" in proc.stderr

    def test_short_secret_refused(self):
        proc = _run("tooshort")
        assert proc.returncode != 0
        assert "JWT_SECRET" in proc.stderr

    def test_ci_style_short_secret_refused(self):
        """Секрет вида test-secret-for-ci короче минимума."""
        proc = _run("test-secret-for-ci")
        assert proc.returncode != 0

    def test_strong_secret_accepted(self):
        assert _run(GOOD_SECRET).returncode == 0


class TestNonProductionIsLenient:
    """В разработке и тестах слабый секрет допустим — иначе не запуститься."""

    def test_debug_allows_placeholder(self):
        assert _run("CHANGE-ME-IN-PRODUCTION", debug="true").returncode == 0

    def test_testing_allows_placeholder(self):
        assert _run("CHANGE-ME-IN-PRODUCTION", testing="true").returncode == 0
