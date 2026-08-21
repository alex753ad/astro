/**
 * PricingPage — публичная страница тарифов.
 * Маршрут: /pricing, доступна без авторизации.
 */

import { Link, useNavigate } from 'react-router-dom';
import MotionButton from '../components/MotionButton';
import { TIERS } from '../constants';

const DISPLAY = "'Space Grotesk', system-ui, sans-serif";
const BODY = "'Inter', system-ui, sans-serif";

export default function PricingPage({ currentUser, onShowAuth }) {
  const navigate = useNavigate();

  const handleChoose = () => {
    if (currentUser) navigate('/profile');
    else if (onShowAuth) onShowAuth();
    else navigate('/home');
  };

  return (
    <div style={s.page}>
      <div style={s.inner}>
        <h1 style={s.h1}>Тарифы</h1>
        <p style={s.sub}>
          Разовая оплата за один месяц доступа. Автопродления нет — по окончании
          месяца доступ закрывается, продлить можно новой оплатой.
        </p>

        <div style={s.grid}>
          {TIERS.map((t) => (
            <div key={t.id} style={s.card(t.recommended)}>
              {t.recommended && <span style={s.badge}>Рекомендуем</span>}
              <div style={s.tierName}>{t.label}</div>
              <div style={s.price}>{t.price}</div>
              {t.upsellFrom && <div style={s.upsell}>{t.upsellFrom}</div>}
              <ul style={s.features}>
                {t.features.map((f) => (
                  <li key={f} style={s.featureItem}>
                    <span style={s.checkIcon}>✓</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <MotionButton
                level={t.recommended ? 'primary' : 'secondary'}
                style={{
                  ...(t.recommended ? s.ctaPrimary : s.ctaSecondary),
                  ...(t.id === 'premium' ? s.ctaDisabled : {}),
                }}
                onClick={t.id === 'premium' ? undefined : handleChoose}
                disabled={t.id === 'premium'}
              >
                {t.id === 'premium' ? 'Скоро' : t.id === 'free' ? 'Начать бесплатно' : `Выбрать «${t.label}»`}
              </MotionButton>
            </div>
          ))}
        </div>

        <div style={s.accessBlock}>
          <h2 style={s.accessTitle}>Как получить доступ</h2>
          <p style={s.accessText}>
            Доступ открывается автоматически сразу после оплаты, в личном кабинете
            на astreatime.ru. Ничего скачивать и ждать не нужно.
          </p>
        </div>

        <p style={s.legal}>
          Оплата разовая, за один месяц. Автоматических списаний нет, по окончании
          месяца доступ закрывается, продление — новой оплатой.
        </p>

        <Link to="/terms" style={s.offerLink}>Публичная оферта →</Link>
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
  inner: { maxWidth: 1080, margin: '0 auto' },
  h1: {
    fontFamily: DISPLAY,
    fontSize: 32,
    fontWeight: 700,
    margin: '0 0 12px',
    textAlign: 'center',
  },
  sub: {
    fontSize: 15,
    lineHeight: 1.6,
    color: 'var(--text-secondary)',
    textAlign: 'center',
    maxWidth: 620,
    margin: '0 auto 40px',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
    gap: 20,
    marginBottom: 48,
  },
  card: (recommended) => ({
    position: 'relative',
    display: 'flex',
    flexDirection: 'column',
    background: 'var(--bg-card)',
    border: recommended ? '1.5px solid var(--accent)' : '1px solid var(--border)',
    borderRadius: 20,
    boxShadow: recommended ? '0 0 15px rgba(139,92,246,0.10)' : 'none',
    padding: '24px 20px',
  }),
  badge: {
    position: 'absolute',
    top: -12,
    left: 20,
    background: 'var(--accent)',
    color: '#fff',
    fontFamily: DISPLAY,
    fontSize: 11,
    fontWeight: 700,
    padding: '3px 10px',
    borderRadius: 8,
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  tierName: {
    fontFamily: DISPLAY,
    fontSize: 18,
    fontWeight: 600,
    marginBottom: 6,
  },
  price: {
    fontFamily: DISPLAY,
    fontSize: 26,
    fontWeight: 700,
    marginBottom: 10,
  },
  upsell: {
    fontSize: 12,
    fontWeight: 600,
    color: 'var(--accent-glow)',
    marginBottom: 10,
  },
  features: {
    listStyle: 'none',
    margin: '0 0 20px',
    padding: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: 9,
    flexGrow: 1,
  },
  featureItem: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 8,
    fontSize: 13,
    lineHeight: 1.45,
  },
  checkIcon: { color: 'var(--accent)', flexShrink: 0 },
  ctaPrimary: {
    width: '100%',
    height: 44,
    border: 'none',
    borderRadius: 16,
    background: 'var(--accent)',
    color: '#fff',
    fontFamily: DISPLAY,
    fontSize: 14,
    fontWeight: 700,
    cursor: 'pointer',
  },
  ctaSecondary: {
    width: '100%',
    height: 44,
    border: '1.5px solid var(--border)',
    borderRadius: 16,
    background: 'var(--bg-card)',
    color: 'var(--text-primary)',
    fontFamily: DISPLAY,
    fontSize: 14,
    fontWeight: 700,
    cursor: 'pointer',
  },
  ctaDisabled: {
    background: 'var(--bg-card)',
    color: 'var(--text-secondary)',
    border: '1.5px solid var(--border)',
    opacity: 0.6,
    cursor: 'default',
  },
  accessBlock: {
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: 16,
    padding: '20px 24px',
    marginBottom: 24,
    maxWidth: 620,
    marginLeft: 'auto',
    marginRight: 'auto',
    textAlign: 'center',
  },
  accessTitle: {
    fontFamily: DISPLAY,
    fontSize: 16,
    fontWeight: 600,
    margin: '0 0 8px',
  },
  accessText: {
    fontSize: 14,
    lineHeight: 1.6,
    color: 'var(--text-secondary)',
    margin: 0,
  },
  legal: {
    fontSize: 13,
    color: 'var(--text-secondary)',
    textAlign: 'center',
    maxWidth: 620,
    margin: '0 auto 16px',
  },
  offerLink: {
    display: 'block',
    textAlign: 'center',
    color: 'var(--accent)',
    fontSize: 14,
    fontWeight: 600,
    textDecoration: 'none',
  },
};
