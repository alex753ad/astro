/**
 * RequisitesPage — реквизиты и контакты продавца.
 * Маршрут: /requisites, доступна без авторизации.
 * Требование ЮKassa («Контакты и реквизиты») и ст. 9 ЗоЗПП.
 */

const DISPLAY = "'Space Grotesk', system-ui, sans-serif";
const BODY = "'Inter', system-ui, sans-serif";

const ROWS = [
  { label: 'Продавец', value: 'Оносова Наталья Юрьевна' },
  { label: 'Статус', value: 'Самозанятая, плательщик налога на профессиональный доход' },
  { label: 'ИНН', value: '615011483048' },
  { label: 'Город', value: 'г. Новочеркасск, Ростовская область' },
  { label: 'Телефон', value: '+7 910 655-65-03' },
  { label: 'Email', value: 'carearistea@mail.ru' },
  { label: 'Поддержка', value: 'Ежедневно, без выходных. Ответ в течение 24 часов.' },
];

export default function RequisitesPage() {
  return (
    <div style={s.page}>
      <div style={s.inner}>
        <h1 style={s.h1}>Реквизиты и контакты</h1>
        <div style={s.card}>
          {ROWS.map((r) => (
            <div key={r.label} style={s.row}>
              <div style={s.label}>{r.label}</div>
              <div style={s.value}>{r.value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const s = {
  page: {
    minHeight: '100vh',
    background: 'var(--bg)',
    color: 'var(--text-primary)',
    fontFamily: BODY,
    padding: '48px 16px 64px',
  },
  inner: { maxWidth: 560, margin: '0 auto' },
  h1: {
    fontFamily: DISPLAY,
    fontSize: 28,
    fontWeight: 700,
    margin: '0 0 24px',
    textAlign: 'center',
  },
  card: {
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: 20,
    padding: '8px 24px',
  },
  row: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    padding: '14px 0',
    borderBottom: '1px solid var(--border)',
  },
  label: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
    color: 'var(--text-secondary)',
  },
  value: {
    fontSize: 15,
    lineHeight: 1.5,
  },
};
