/**
 * digestAccess.js — кому показывать «День недельного дайджеста».
 *
 * Письмо шлёт только Лире и Ориону: фильтр `User.tier.in_(["pro", "premium"])`
 * в `send_weekly_digest_task` (backend/tasks.py). На остальных тарифах выбор
 * дня ни на что не влияет, поэтому пункт скрыт (решение владельца 27.09.2026).
 * Тариф неизвестен (нет сети) — тоже скрыт: обещать письмо наугад нельзя.
 *
 * ⚠️ Копия серверного списка; синхронность держит digestAccess.test.js,
 * читающий tasks.py. Разойдутся — человек выберет день письма, которое не придёт.
 */

export const DIGEST_TIERS = ['pro', 'premium'];

export function showsDigestDay(tier) {
  return DIGEST_TIERS.includes(tier);
}
