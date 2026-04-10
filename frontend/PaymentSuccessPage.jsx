/**
 * PaymentSuccessPage — shown after successful Stripe checkout redirect.
 *
 * Route: /payment/success?session_id=...
 */

import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import useAuth from '../hooks/useAuth';

export default function PaymentSuccessPage() {
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get('session_id');
  const { authFetch, user } = useAuth();
  const [verified, setVerified] = useState(false);

  // Poll /profile/subscription briefly to get the updated tier
  useEffect(() => {
    let attempts = 0;
    const poll = setInterval(async () => {
      attempts++;
      try {
        const data = await authFetch('/api/v1/profile/subscription');
        if (data.tier !== 'free') {
          setVerified(true);
          clearInterval(poll);
        }
      } catch {
        /* ignore */
      }
      if (attempts >= 6) clearInterval(poll); // stop after ~12s
    }, 2000);
    return () => clearInterval(poll);
  }, [authFetch]);

  return (
    <div style={{ maxWidth: 480, margin: '80px auto', padding: '0 16px', textAlign: 'center' }}>
      <div className="glass-card p-10">
        <div style={{ fontSize: 52, marginBottom: 16 }}>🎉</div>
        <h1 className="font-display text-2xl font-bold mb-3">
          Подписка активирована!
        </h1>
        <p className="text-brand-muted mb-8" style={{ lineHeight: 1.65 }}>
          {verified
            ? `Добро пожаловать в Pro! Теперь вам доступны транзиты, безлимитные интерпретации и история карт.`
            : `Оплата прошла успешно. Обновляем ваш аккаунт…`}
        </p>

        {!verified && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: 6, marginBottom: 24 }}>
            {[0,1,2].map(i => (
              <span key={i} style={{
                width: 8, height: 8, borderRadius: 4,
                background: 'var(--accent, #7C6CFF)',
                animation: `pulse 1.2s ease ${i * 0.3}s infinite`,
              }} />
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
          <Link
            to="/"
            style={{
              padding: '12px 24px', borderRadius: 10,
              background: 'linear-gradient(135deg, #7C6CFF, #A78BFA)',
              color: '#fff', fontWeight: 700, fontSize: 14, textDecoration: 'none',
            }}
          >
            Рассчитать карту →
          </Link>
          <Link
            to="/profile"
            style={{
              padding: '12px 24px', borderRadius: 10,
              border: '1px solid var(--border, #1E2235)',
              color: 'var(--text-primary)', fontSize: 14, textDecoration: 'none',
            }}
          >
            Перейти в профиль
          </Link>
        </div>
      </div>
      <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.3}}`}</style>
    </div>
  );
}
