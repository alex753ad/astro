# Карта: ядро транзитов `backend/sky.py` и его вызовы

Шаг 4 аудита (`docs/audit_unified_model.md`, 8.3). Без флага `sky_event` всё ниже не вызывается.
Обновлять, когда раздел переходит на ядро или появляется новый ключ кэша.

## sky.py
- `compute` — события на отрезке без кэша; `_chunk` — UTC-месяц, кэш `sky:v2:{chart}:{YYYY-MM}` (zlib).
- `sky_events(chart, from, to)` — события, пересекающие отрезок, из чанков.
- `find_event` — событие по `peak_date` карточки; `interpret_facts` — факты разбора.
- `warm` / `warm_chart` — прогрев трёх месяцев (`tasks.sky_warm`: beat и после сохранения карты).

## Кто зовёт `sky_events`
- главное событие — `day_event._sky_touches ← _candidates` (4.2);
- прогноз дня и лунный — `forecast/facts._moon_touches`, `_warning_touches` (4.3);
- лента — `feed/builder._sky_chunk ← transit_cards` (4.4);
- чат — `interpretation/rag._sky_transits_block` (4.6);
- PDF — `pdf_reports/sections._sky_main_transits` (4.7).
- веб `/transits` — `transit/engine._sky_window_events ← window_events` (4.8); прогрев года — `sky.warm_year`.
- CRM (дашборд, «Пора напомнить», групповой прогноз, письмо клиентам, бриф) — `crm/dashboard_router._sky_crm_events ← crm_events` (4.12); флаг — по астрологу, `crm_sky`.
- пилотные письма — `pilot/cron._sky_windows`; письмо дня 7 — `lifecycle_emails._transit_count`; строка утреннего пуша — `push/cron._daily_body` (4.12). Старые пуши «вошёл в орб», «за 4°», «тройное касание» под флагом не собираются (`push/cron._collect_candidates`).
- `find_event`, `interpret_facts` ← `transit/engine.interpret_event_facts` ← ручка разбора (4.5), чат, Consistency.

## Флаг
- `day_event._sky_on(chart)` — по сессии ORM-карты; у dict/SimpleNamespace — выключен.
  Поэтому ручки ленты, чата и PDF решают флаг по ORM-карте и передают `sky` явно.
- `forecast/facts.sky_on` — то же через атрибут модуля (его подменяет `consistency_eval --sky on`).

## Ключи кэша под флагом (рядом со старыми)
| Раздел | Без флага | Под флагом |
|---|---|---|
| лента | `feed:v4:…` | `feed:v5-sky{sky.CACHE_VERSION}:…` |
| прогноз дня / лунный | `forecast_today:v6`, `forecast_lunation:v4` | `…:v6-sky`, `…:v4-sky` |
| разбор транзита | `transit_interp:v8:{chart}:{tp}:{np}:{asp}:{дата}` | `transit_interp:v11:{chart}:{event.key}:{пояс}` |
| чат | `chat_transits:v7`, `chat_p1:v2` | `chat_transits:v8-sky`, `chat_p1:v2-sky` |
| PDF | `transits:v7:{YYYY-MM}:{tier}` | `transits:v7-sky:…` (и отпечаток отчёта) |
| веб `/transits` | `transit:v5:…` | `transit:v6-sky:…:{пояс}` |

## Формулировки дат
`transit/prompts.touches_ru`, `period_ru`, `gaps_ru` — одни для разбора, чата и PDF
(год — у последней даты года; в перерывах — отдельно, `docs/decisions.md`).
