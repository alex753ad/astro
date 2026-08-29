import { Link } from 'react-router-dom';

/**
 * NotFoundPage — catch-all для несуществующих маршрутов.
 * Без него React Router рендерил пустой <Routes> без совпадения:
 * белая страница с кодом 200 (SPA-роутинг не даёт браузеру дойти
 * до настоящего 404 от сервера).
 */

const DISPLAY = "'Space Grotesk', system-ui, sans-serif";
const BODY = "'Inter', system-ui, sans-serif";

export default function NotFoundPage() {
  return (
    <div style={s.page}>
      <div style={s.inner}>
        <div style={s.code}>404</div>
        <h1 style={s.h1}>Страница не найдена</h1>
        <p style={s.p}>Такого адреса нет, либо он был перемещён.</p>
        <Link to="/" style={s.link}>На главную</Link>
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
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '48px 16px',
  },
  inner: { maxWidth: 420, textAlign: 'center' },
  code: {
    fontFamily: DISPLAY,
    fontSize: 56,
    fontWeight: 700,
    color: 'var(--text-secondary)',
    marginBottom: 8,
  },
  h1: {
    fontFamily: DISPLAY,
    fontSize: 22,
    fontWeight: 700,
    margin: '0 0 12px',
  },
  p: {
    fontSize: 15,
    lineHeight: 1.5,
    color: 'var(--text-secondary)',
    margin: '0 0 24px',
  },
  link: {
    display: 'inline-block',
    background: 'var(--accent)',
    color: '#fff',
    fontSize: 14,
    fontWeight: 600,
    padding: '10px 20px',
    borderRadius: 12,
    textDecoration: 'none',
  },
};
