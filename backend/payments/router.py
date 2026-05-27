"""DEPRECATED: этот роутер дублирует payments_router.py.

Используй payments_router.py — он полнее (содержит handle_subscription_deleted
и более подробное логирование).

Подключение в main.py (или app factory):
    from backend.payments.payments_router import router as payments_router
    app.include_router(payments_router)

НЕ подключай оба роутера одновременно — оба используют prefix /api/v1/payments,
что создаст дублирующиеся маршруты, в т.ч. два обработчика /webhook.
Stripe будет слать событие на один URL, но FastAPI зарегистрирует его дважды.
"""

# Реэкспорт для обратной совместимости
from backend.payments.payments_router import router  # noqa: F401
