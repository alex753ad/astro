"""Регрессия: в проде приложение не поднимается без ключей ЮKassa.

До 23.08.2026 пустая пара YOOKASSA_SHOP_ID/YOOKASSA_SECRET_KEY считалась
нормой — платежи просто не активны, /payments/checkout отвечает 503. Это было
удобно, пока оплату не запустили. Сейчас магазин зарегистрирован и оплата
объявлена пользователям, поэтому пустой .env означает молча неработающую
кнопку «оплатить», о которой узнаёшь от пользователя.

Тот же набор правил продублирован в deploy/opt-astro/05-update.sh (список
_required): проверка только в приложении означает, что о проблеме узнаёшь на
середине деплоя, когда старый контейнер уже погашен — так прод падал дважды,
см. CLAUDE.md. Синхронность этих двух мест проверяется тестом ниже.

Проверка выполняется на импорте backend.main, поэтому каждый случай —
отдельный процесс.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from backend.tests.prod_env import PROD_STARTUP_ENV

GOOD_SECRET = "x7Kp2mQvR9dLwF4tYbN6hJ3sZ8cV5gA1nE0uT" + "qWmXyPoI"  # gitleaks:allow — тестовая фикстура

UPDATE_SH = Path(__file__).resolve().parents[2] / "deploy" / "opt-astro" / "05-update.sh"


def _run(*, shop_id=None, secret_key=None, debug="false", testing="false"):
    """Стартовать backend.main отдельным процессом с заданной парой ключей.

    None означает «переменной нет вовсе» — именно это и проверяется, поэтому
    из PROD_STARTUP_ENV соответствующий ключ убирается, а не затирается пустым.
    """
    env = {
        "JWT_SECRET": GOOD_SECRET,
        "DEBUG": debug,
        "TESTING": testing,
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        **PROD_STARTUP_ENV,
    }
    env.pop("YOOKASSA_SHOP_ID", None)
    env.pop("YOOKASSA_SECRET_KEY", None)
    if shop_id is not None:
        env["YOOKASSA_SHOP_ID"] = shop_id
    if secret_key is not None:
        env["YOOKASSA_SECRET_KEY"] = secret_key

    return subprocess.run(
        [sys.executable, "-c", "import backend.main"],
        capture_output=True, text=True, env=env, timeout=300,
    )


class TestProductionRequiresYookassa:

    def test_both_missing_refused(self):
        """Главный случай: раньше проходил молча и отключал оплату."""
        proc = _run()
        assert proc.returncode != 0, "пустой .env больше не должен тихо отключать оплату"
        assert "YOOKASSA_SHOP_ID" in proc.stderr

    def test_only_shop_id_refused(self):
        proc = _run(shop_id="1442186")
        assert proc.returncode != 0
        assert "YOOKASSA" in proc.stderr

    def test_only_secret_key_refused(self):
        proc = _run(secret_key="live_whatever")
        assert proc.returncode != 0
        assert "YOOKASSA" in proc.stderr

    def test_empty_string_counts_as_missing(self):
        """Переменная есть, но пустая — оплата так же не работает."""
        proc = _run(shop_id="", secret_key="")
        assert proc.returncode != 0
        assert "YOOKASSA" in proc.stderr

    def test_both_present_starts(self):
        proc = _run(shop_id="1442186", secret_key="live_stub_not_a_real_key")
        assert proc.returncode == 0, proc.stderr

    def test_test_key_still_refused(self):
        """Существующий guard про тестовый ключ не потерялся."""
        proc = _run(shop_id="1442186", secret_key="test_stub")
        assert proc.returncode != 0
        assert "test_" in proc.stderr or "тестовый" in proc.stderr


class TestNonProductionIsLenient:
    """Без этого локальная разработка и CI без ключей магазина не запустятся."""

    @pytest.mark.parametrize("flag", ["DEBUG", "TESTING"])
    def test_missing_keys_allowed_outside_production(self, flag):
        kwargs = {"debug": "false", "testing": "false", flag.lower(): "true"}
        assert _run(**kwargs).returncode == 0


class TestDeployScriptStaysInSync:
    """Гвард обязан быть в ОБОИХ местах.

    Отсутствие второй проверки уже дважды роняло прод: приложение падало на
    старте, когда старый контейнер был погашен, а деплой-скрипт об этом не
    знал и до проверки не доходил. Тест сверяет не текст, а факт наличия
    обеих переменных в обязательном списке _required.
    """

    def test_required_list_contains_both_variables(self):
        script = UPDATE_SH.read_text(encoding="utf-8")
        m = re.search(r"for _required in(.*?); do", script, re.DOTALL)
        assert m, "цикл _required не найден — 05-update.sh изменился, проверьте preflight"
        required = m.group(1)
        assert "YOOKASSA_SHOP_ID" in required, \
            "YOOKASSA_SHOP_ID обязателен в main.py, но не в 05-update.sh — рассинхрон"
        assert "YOOKASSA_SECRET_KEY" in required, \
            "YOOKASSA_SECRET_KEY обязателен в main.py, но не в 05-update.sh — рассинхрон"
