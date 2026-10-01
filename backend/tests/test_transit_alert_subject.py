"""Тема письма «Важный транзит»: сфера целиком, без обрезки на союзе.

До 01.10.2026 сфера резалась по первой запятой, и тема выходила
«Сатурн: твои границы и то — как использовать напряжение».
"""
import re

import pytest

from backend.transit.engine import ASPECT_TONE, NATAL_SPHERE, _build_transit_alert_subject

_DANGLING = re.compile(r"(?:^|\s)(?:и|а|но|или|то|что|за)$")


@pytest.mark.parametrize("pair", sorted(NATAL_SPHERE))
@pytest.mark.parametrize("aspect", sorted(ASPECT_TONE))
def test_subject_keeps_sphere_whole(pair, aspect):
    sphere = NATAL_SPHERE[pair].split(" — ")[0]
    assert not _DANGLING.search(sphere), sphere
    assert sphere in _build_transit_alert_subject(pair[0], pair[1], aspect, "Планета")
