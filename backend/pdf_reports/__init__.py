"""PDF-отчёты по тарифам (решение владельца 28–29.09.2026, TASKS п. 6).

sections.py — из чего состоит отчёт тарифа и откуда берутся тексты;
build.py    — сборка в Celery (tasks.build_pdf_report) и хранение файла;
router.py   — ручки /chart/{id}/pdf-reports и /pdf-reports/{id}.

Правила — docs/tariffs.md, «PDF по тарифам».
"""
