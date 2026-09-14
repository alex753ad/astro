"""Сессионные ручки /auth/ не должны стоять за ЗАДЕРЖИВАЮЩИМ лимитом.

Зона `auth` (`rate=1r/s`, `burst` БЕЗ `nodelay`) не отбивает лишние запросы, а
выстраивает их в очередь по секунде на каждый. Для входа и рассылки кода это
задумано; для `/auth/refresh`, `/auth/me` и `/auth/sse-ticket` — нет: их
дёргает каждая сессия при каждом старте.

Что ломалось, пока они попадали под общий префикс (приёмка мобильного
приложения 07.09.2026): холодный старт монтирует три экрана разом, все
получают 401 по протухшему access и сходятся в один `/auth/refresh`; тот
встаёт в очередь — и ждут все три экрана. Замер на боевом сервере: зона `api`
отвечала за 1.2 с, refresh — за 4.1 с, а 12 параллельных refresh — 1.9…11.9 с
и 429. Экраны упирались в свой 15-секундный таймаут, показывали «Сервер не
отвечает», и приложение оставалось в тупике до переустановки.

Тест текстовый, как `TestDeployScriptStaysInSync`: файл конфига в CI не
исполняется, а разъехаться с замыслом может молча — заметно это станет только
на устройстве и только на холодном старте.
"""

from __future__ import annotations

import re
from pathlib import Path

_NGINX = Path(__file__).resolve().parents[2] / "deploy" / "opt-astro" / "nginx"

# ⚠️ Блоки проксирования переехали 14.09.2026 из astreatime.conf в сниппет.
# Причина — разделение на канонический и редиректный server: в nginx location
# между server-блоками не наследуются, и без сниппета эти 219 строк пришлось бы
# держать в файле дважды (разбор — CLAUDE.md, «/api/ исключён из редиректа»).
#
# Тест ходит СЮДА, а не в astreatime.conf. Если блоки когда-нибудь вернут
# обратно, правильная реакция — поменять путь здесь, а не ослабить проверки:
# они закрывают отказ, который виден только на устройстве и только на холодном
# старте.
CONF = _NGINX / "snippets" / "backend-locations.conf"
SITE = _NGINX / "astreatime.conf"

SESSION_PATHS = ("refresh", "me", "sse-ticket")


def _blocks(text: str) -> dict[str, str]:
    """{заголовок location: тело до первой закрывающей скобки уровня}."""
    out: dict[str, str] = {}
    for match in re.finditer(r"^\s{4}location\s+([^{]+?)\s*\{", text, re.M):
        start = match.end()
        depth = 1
        i = start
        while depth and i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        out[match.group(1)] = text[start:i]
    return out


class TestSnippetIsWiredIntoBothServers:
    """Сниппет обязан быть подключён в оба https-сервера.

    ⚠️ Иначе проверки ниже станут вакуумными: они прочитают правильный файл и
    останутся зелёными, хотя на неканонических хостах (www, старый бренд) ручек
    /auth/ не будет вовсе. На www ходит мобильное приложение — отказ проявился
    бы только у пользователей APK.
    """

    def test_included_twice(self):
        site = SITE.read_text(encoding="utf-8")
        include = "include /etc/nginx/snippets/backend-locations.conf;"
        assert site.count(include) == 2, (
            f"сниппет подключён {site.count(include)} раз(а), ожидалось 2 — "
            "канонический сервер и редиректный"
        )

    def test_redirect_server_does_not_swallow_api(self):
        """В редиректном сервере 301 обязан стоять ПОСЛЕ include.

        Порядок в файле для nginx не важен (префиксные location выбираются по
        длине совпадения), но `location /` с `return 301` и include рядом —
        место, где легко потерять одно из двух при правке.
        """
        site = SITE.read_text(encoding="utf-8")
        assert "return 301 https://aristeatime.ru$request_uri;" in site


class TestAuthZoneStaysStrict:
    def test_prefix_auth_block_is_still_delaying(self):
        """У зоны входа/регистрации `nodelay` быть НЕ должно — очередь тут к месту."""
        body = _blocks(CONF.read_text(encoding="utf-8"))["/api/v1/auth/"]
        assert "zone=auth" in body
        assert "nodelay" not in body


class TestSessionEndpointsAreNotDelayed:
    def test_session_endpoints_have_their_own_block(self):
        blocks = _blocks(CONF.read_text(encoding="utf-8"))
        header = next(
            (h for h in blocks if h.startswith("~") and "/auth/" in h),
            None,
        )
        assert header, "нет отдельного location для сессионных ручек /auth/"
        for name in SESSION_PATHS:
            assert name in header, f"{name} не покрыт: {header}"

    def test_session_endpoints_are_in_the_fast_zone(self):
        blocks = _blocks(CONF.read_text(encoding="utf-8"))
        header = next(h for h in blocks if h.startswith("~") and "/auth/" in h)
        body = blocks[header]
        assert "zone=api" in body, "сессионные ручки обязаны быть в общей зоне"
        assert "nodelay" in body, "без nodelay запросы снова встанут в очередь"

    def test_block_is_regex_so_it_wins_over_the_prefix(self):
        """Префиксный location проиграл бы: nginx выбирает regex раньше."""
        blocks = _blocks(CONF.read_text(encoding="utf-8"))
        header = next(h for h in blocks if "/auth/" in h and h.startswith("~"))
        assert header.startswith("~ ^/api/v1/auth/"), header
        assert header.endswith("$"), "выражение обязано быть заякорено с конца"
