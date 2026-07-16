// frontend/src/pages/TermsPage.jsx
// Маршрут: /terms

import { Link } from 'react-router-dom';

const s = {
  page:    { minHeight: '100vh', background: 'var(--bg-deeper)', color: 'var(--border)', fontFamily: "'Inter', system-ui, sans-serif", padding: '48px 20px' },
  inner:   { maxWidth: 760, margin: '0 auto' },
  h1:      { fontSize: 32, fontWeight: 800, color: 'var(--accent-glow)', marginBottom: 8 },
  updated: { fontSize: 13, color: 'var(--text-secondary)', marginBottom: 40 },
  h2:      { fontSize: 18, fontWeight: 700, color: 'var(--accent-glow)', margin: '32px 0 12px' },
  p:       { fontSize: 15, lineHeight: 1.8, color: 'var(--border)', margin: '0 0 12px' },
  card:    { background: 'var(--bg-card)', border: '1px solid var(--text-primary)', borderRadius: 10, padding: '16px 20px', marginBottom: 10 },
  label:   { fontSize: 12, fontWeight: 700, color: 'var(--accent-glow)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 },
  warn:    { background: 'var(--text-primary)', border: '1px solid var(--color-warning)', borderRadius: 10, padding: '16px 20px', marginBottom: 10, color: 'var(--color-warning)', fontSize: 14, lineHeight: 1.7 },
  footer:  { marginTop: 48, paddingTop: 24, borderTop: '1px solid var(--bg-card)', display: 'flex', gap: 20, fontSize: 13 },
  link:    { color: 'var(--accent-glow)', textDecoration: 'none' },
};

export default function TermsPage() {
  return (
    <div style={s.page}>
      <div style={s.inner}>
        <h1 style={s.h1}>Условия использования</h1>
        <div style={s.updated}>Последнее обновление: 1 июня 2026 г.</div>

        <p style={s.p}>
          Используя сайт astreatime.ru и сервис Astrea Timeline, вы принимаете настоящие Условия использования.
          Если вы не согласны с условиями — пожалуйста, не используйте сервис.
        </p>

        <h2 style={s.h2}>1. Описание сервиса</h2>
        <p style={s.p}>
          Astrea Timeline — онлайн-сервис астрологических расчётов и интерпретаций. Сервис предоставляет:
        </p>
        <p style={s.p}>— Расчёт натальной карты на основе Swiss Ephemeris.</p>
        <p style={s.p}>— AI-интерпретации планет, домов, аспектов и транзитов.</p>
        <p style={s.p}>— Персональный астрологический планер и дайджесты.</p>
        <p style={s.p}>— Лунный календарь и прогнозы транзитов.</p>

        <h2 style={s.h2}>2. Тарифные планы</h2>
        {[
          { label: 'Free', text: 'Расчёт карты, базовые транзиты. Бесплатно, без ограничения по времени.' },
          { label: 'Lite', text: 'Полные транзиты, AI-интерпретации ключевых периодов, лунный календарь. Ежемесячная/годовая подписка.' },
          { label: 'Pro', text: 'Все функции Lite + планер, еженедельный дайджест, приоритетный AI. Ежемесячная/годовая подписка.' },
          { label: 'Premium', text: 'Все функции Pro + CRM-кабинет астролога, аналитика клиентской базы. Ежемесячная/годовая подписка.' },
        ].map(({ label, text }) => (
          <div key={label} style={s.card}>
            <div style={s.label}>{label}</div>
            <p style={{ ...s.p, margin: 0 }}>{text}</p>
          </div>
        ))}
        <p style={s.p}>
          Оплата производится через Robokassa. Подписка автоматически продлевается. Вы можете отменить
          подписку в любой момент в личном кабинете — доступ сохраняется до конца оплаченного периода.
          Возврат средств — в течение 14 дней с момента первой оплаты тарифа при обращении на support@astreatime.ru.
        </p>

        <h2 style={s.h2}>3. Отказ от ответственности</h2>
        <div style={s.warn}>
          ⚠️ <strong>Астрология не является наукой.</strong> Результаты расчётов и интерпретации носят
          исключительно развлекательный и информационный характер. Astrea Timeline не несёт ответственности
          за решения, принятые на основе астрологических прогнозов.
        </div>
        <div style={s.warn}>
          🏥 <strong>Не является медицинской консультацией.</strong> Ничто на сайте не является медицинским
          советом, диагнозом или лечением. При проблемах со здоровьем обращайтесь к врачу.
        </div>
        <div style={s.warn}>
          ⚖️ <strong>Не является юридической консультацией.</strong> Контент сайта не заменяет
          профессиональные юридические, финансовые или психологические консультации.
        </div>

        <h2 style={s.h2}>4. Правила использования</h2>
        <p style={s.p}>— Запрещено использовать сервис для незаконных целей.</p>
        <p style={s.p}>— Запрещено перепродавать доступ к сервису третьим лицам.</p>
        <p style={s.p}>— Запрещено пытаться обойти технические ограничения или взломать сервис.</p>
        <p style={s.p}>— Один аккаунт — один пользователь. Совместное использование аккаунта не допускается.</p>

        <h2 style={s.h2}>5. Интеллектуальная собственность</h2>
        <p style={s.p}>
          Весь контент сайта (дизайн, тексты, AI-интерпретации, алгоритмы) является интеллектуальной
          собственностью Astrea Timeline. Личные данные карты принадлежат пользователю.
          Копирование и распространение AI-интерпретаций без указания источника не допускается.
        </p>

        <h2 style={s.h2}>6. Ограничение ответственности</h2>
        <p style={s.p}>
          Сервис предоставляется «как есть». Мы не гарантируем бесперебойную работу и не несём
          ответственности за упущенную выгоду или косвенные убытки, возникшие в связи с использованием сервиса.
          Максимальная ответственность ограничена суммой, уплаченной за подписку за последние 3 месяца.
        </p>

        <h2 style={s.h2}>7. Изменения условий</h2>
        <p style={s.p}>
          Мы можем изменять настоящие Условия. При существенных изменениях уведомим по email за 14 дней.
          Продолжение использования сервиса означает принятие новых условий.
        </p>

        <h2 style={s.h2}>8. Применимое право</h2>
        <p style={s.p}>
          Настоящие Условия регулируются законодательством Российской Федерации.
        </p>

        <h2 style={s.h2}>9. Контакт</h2>
        <p style={s.p}>
          По вопросам: <a href="mailto:support@astreatime.ru" style={s.link}>support@astreatime.ru</a>
        </p>

        <div style={s.footer}>
          <Link to="/" style={s.link}>← Главная</Link>
          <Link to="/privacy" style={s.link}>Политика конфиденциальности</Link>
        </div>
      </div>
    </div>
  );
}
