"""scripts/consistency_eval.py берёт внутренности backend (_MONTHS_RU,
PLANET_NAMES_RU, _speed_at…) ленивыми импортами внутри функций — тесты бэкенда
их не видят, а сломанный импорт обнуляет проверку молча: c3 «сравнено=0» с
ошибкой ImportError в строке (07.10.2026, шаг 7.3 удалил ASPECT_LABELS_RU).
Удаляя или переименовывая имя в backend — grep и по scripts/.
"""

import ast
import importlib
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "consistency_eval.py"


def test_every_backend_name_the_script_imports_exists():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    missing = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("backend"):
            mod = importlib.import_module(node.module)
            for alias in node.names:
                if not hasattr(mod, alias.name):
                    try:  # подмодуль пакета: from backend.transit import prompts
                        importlib.import_module(f"{node.module}.{alias.name}")
                    except ImportError:
                        missing.append(f"{node.module}.{alias.name} (строка {node.lineno})")
    assert not missing, missing
