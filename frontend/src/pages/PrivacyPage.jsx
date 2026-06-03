// frontend/src/pages/PrivacyPage.jsx
// Маршрут: /privacy

import { Link } from 'react-router-dom';

const s = {
  page:    { minHeight: '100vh', background: '#0f172a', color: '#e2e8f0', fontFamily: "'Inter', system-ui, sans-serif", padding: '48px 20px' },
  inner:   { maxWidth: 760, margin: '0 auto' },
  h1:      { fontSize: 32, fontWeight: 800, color: '#a78bfa', marginBottom: 8 },
  updated: { fontSize: 13, color: '#64748b', marginBottom: 40 },
  h2:      { fontSize: 18, fontWeight: 700, color: '#c4b5fd', margin: '32px 0 12px' },
  p:       { fontSize: 15, lineHeight: 1.8, color: '#cbd5e1', margin: '0 0 12px' },
  card:    { background: '#1e293b', border: '1px solid #334155', borderRadius: 10, padding: '16px 20px', marginBottom: 10 },
  label:   { fontSize: 12, fontWeight: 700, color: '#a78bfa', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 },
  footer:  { marginTop: 48, paddingTop: 24, borderTop: '1px solid #1e293b', display: 'flex', gap: 20, fontSize: 13 },
  link:    { color: '#a78bfa', textDecoration: 'none' },
};

export default function PrivacyPage() {
  return (
    <div style={s.page}>
      <div style={s.inner}>
        <h1 style={s.h1}>Политика конфиденциальности</h1>
        <div style={s.updated}>Последнее обновление: 3 июня 2026 г.</div>

        <p style={s.p}>
          Настоящая Политика конфиденциальности описывает, как Astrea Timeline («мы», «сервис») собирает,
          использует и защищает ваши персональные данные при использовании сайта astreatime.ru.
        </p>

        <h2 style={s.h2}>1. Какие данные мы собираем</h2>
        {[
          { label: 'Аккаунт', text: 'Адрес электронной почты, имя (если указано), хешированный пароль.' },
          { label: 'Натальная карта', text: 'Дата рождения, время рождения, место рождения (город, координаты). Без этих данных расчёт карты невозможен.' },
          { label: 'Оплата', text: 'Мы не храним данные банковских карт. Платёжную информацию обрабатывает Robokassa. Мы получаем только статус транзакции и идентификатор подписки.' },
          { label: 'Технические данные', text: 'IP-адрес, тип браузера, страницы посещения — в целях безопасности и аналитики (агрегированно, без привязки к личности).' },
          { label: 'Google Calendar (опционально)', text: 'При добровольном подключении Google Calendar мы запрашиваем доступ к вашим событиям через OAuth 2.0. Мы читаем и создаём события исключительно для отображения в планере Astrea Timeline. Данные не передаются третьим лицам и не используются в рекламных целях. Доступ можно отозвать в любой момент через настройки Google-аккаунта: myaccount.google.com/permissions.' },
        ].map(({ label, text }) => (
          <div key={label} style={s.card}>
            <div style={s.label}>{label}</div>
            <p style={{ ...s.p, margin: 0 }}>{text}</p>
          </div>
        ))}

        <h2 style={s.h2}>2. Как мы используем данные</h2>
        <p style={s.p}>— Расчёт натальной карты и астрологических транзитов с помощью Swiss Ephemeris.</p>
        <p style={s.p}>— Генерация AI-интерпретаций через модели OpenAI / DeepSeek (данные карты передаются обезличенно).</p>
        <p style={s.p}>— Отправка персонализированных писем (прогнозы, дайджесты) через Resend. Вы можете отписаться в любой момент.</p>
        <p style={s.p}>— Обработка платежей и управление подпиской через Robokassa.</p>
        <p style={s.p}>— Синхронизация событий с Google Calendar (только при наличии явного согласия пользователя).</p>
        <p style={s.p}>— Обеспечение безопасности и предотвращение мошенничества.</p>

        <h2 style={s.h2}>3. Хранение данных</h2>
        <p style={s.p}>
          Данные хранятся в базе данных PostgreSQL на платформе Railway (серверы в ЕС/США).
          Соединения защищены TLS 1.3. Пароли хранятся в виде bcrypt-хешей.
          Мы применяем принцип минимальной необходимости данных.
        </p>

        <h2 style={s.h2}>4. Передача третьим лицам</h2>
        {[
          { label: 'Robokassa', text: 'Обработка платежей. Данные карт хранятся исключительно у Robokassa. Политика: robokassa.ru/privacy' },
          { label: 'OpenAI / DeepSeek', text: 'AI-интерпретации. Данные передаются в обезличенном виде (только планеты и аспекты, без имени/email). Политика: openai.com/privacy' },
          { label: 'Resend', text: 'Отправка email-уведомлений.' },
          { label: 'Google LLC', text: 'Интеграция с Google Calendar через OAuth 2.0 — только при наличии явного согласия пользователя. Данные используются исключительно для функций планера. Политика Google: policies.google.com/privacy' },
        ].map(({ label, text }) => (
          <div key={label} style={s.card}>
            <div style={s.label}>{label}</div>
            <p style={{ ...s.p, margin: 0 }}>{text}</p>
          </div>
        ))}
        <p style={s.p}>Мы не продаём и не передаём ваши данные иным третьим лицам.</p>

        <h2 style={s.h2}>5. Ваши права</h2>
        <p style={s.p}>— <strong>Доступ</strong> — запросить копию ваших данных.</p>
        <p style={s.p}>— <strong>Исправление</strong> — изменить данные в личном кабинете.</p>
        <p style={s.p}>— <strong>Удаление</strong> — запросить полное удаление аккаунта и данных (исполняется в течение 30 дней).</p>
        <p style={s.p}>— <strong>Переносимость</strong> — получить данные в машиночитаемом формате.</p>
        <p style={s.p}>— <strong>Отзыв согласия</strong> — отказаться от email-рассылок через ссылку «Отписаться» в любом письме.</p>

        <h2 style={s.h2}>6. Использование данных Google</h2>
        <p style={s.p}>
          Использование и передача информации, полученной от Google API, осуществляется в соответствии
          с <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noopener noreferrer" style={s.link}>Политикой использования данных пользователей Google API</a>,
          включая требования об ограниченном использовании. В частности:
        </p>
        <p style={s.p}>— Данные Google Calendar используются только для предоставления функций планера внутри Astrea Timeline.</p>
        <p style={s.p}>— Мы не используем данные Google для показа рекламы.</p>
        <p style={s.p}>— Мы не передаём данные Google третьим лицам, за исключением случаев, необходимых для работы сервиса.</p>
        <p style={s.p}>— Мы не позволяем людям читать ваши данные Google, если только вы не дали явного согласия или это не требуется по закону.</p>

        <h2 style={s.h2}>7. Cookies</h2>
        <p style={s.p}>
          Мы используем только функциональные cookies (сессия авторизации, тема интерфейса).
          Рекламные и трекинговые cookies не применяются.
        </p>

        <h2 style={s.h2}>8. Изменения политики</h2>
        <p style={s.p}>
          При существенных изменениях мы уведомим вас по email. Продолжение использования сервиса
          после уведомления означает принятие новой редакции.
        </p>

        <h2 style={s.h2}>9. Контакт</h2>
        <p style={s.p}>
          По вопросам обработки данных: <a href="mailto:support@astreatime.ru" style={s.link}>support@astreatime.ru</a>
        </p>

        <div style={s.footer}>
          <Link to="/" style={s.link}>← Главная</Link>
          <Link to="/terms" style={s.link}>Условия использования</Link>
        </div>
      </div>
    </div>
  );
}
