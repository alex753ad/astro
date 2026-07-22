/**
 * GiftPage — страница покупки подарочной подписки.
 * Маршрут: /gift
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import { TIER_NAMES } from '../constants';

const API_BASE = '/api/v1';

const TIERS = [
  {
    id: 'lite',
    name: TIER_NAMES.lite,
    color: 'var(--color-air)',
    desc: 'Карты, лунный календарь, виральные карточки',
    prices: { 1: 790, 3: 2100, 12: 7490 },
  },
  {
    id: 'pro',
    name: TIER_NAMES.pro,
    color: 'var(--accent)',
    desc: 'AI-транзиты, PDF-отчёты, планер на год',
    prices: { 1: 1990, 3: 5490, 12: 18990 },
  },
];

const DURATIONS = [
  { months: 1,  label: '1 месяц' },
  { months: 3,  label: '3 месяца' },
  { months: 12, label: '12 месяцев', badge: '−21%' },
];

const S = {
  page:    { minHeight: '100vh', background: 'var(--bg-deeper)', color: 'var(--border)', fontFamily: "'Inter', system-ui, sans-serif", padding: '40px 16px' },
  inner:   { maxWidth: 720, margin: '0 auto' },
  h1:      { fontSize: 28, fontWeight: 800, margin: '0 0 8px', background: 'linear-gradient(90deg,var(--accent),var(--color-air))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' },
  sub:     { color: 'var(--text-secondary)', marginBottom: 40, fontSize: 16 },
  section: { marginBottom: 32 },
  label:   { fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 },
  row:     { display: 'flex', gap: 12, flexWrap: 'wrap' },
  card:    (selected, color) => ({
    flex: '1 1 160px',
    background: selected ? 'rgba(124,108,255,0.12)' : 'var(--bg-card)',
    border: `2px solid ${selected ? color : 'var(--text-primary)'}`,
    borderRadius: 12,
    padding: '16px 20px',
    cursor: 'pointer',
    transition: 'all .15s',
  }),
  cardName: (color) => ({ fontSize: 18, fontWeight: 800, color, marginBottom: 4 }),
  cardDesc: { fontSize: 13, color: 'var(--text-secondary)' },
  durCard: (selected) => ({
    flex: '1 1 100px',
    background: selected ? 'rgba(124,108,255,0.15)' : 'var(--bg-card)',
    border: `2px solid ${selected ? 'var(--accent)' : 'var(--text-primary)'}`,
    borderRadius: 10,
    padding: '12px 16px',
    cursor: 'pointer',
    textAlign: 'center',
    transition: 'all .15s',
    position: 'relative',
  }),
  badge: { position: 'absolute', top: -10, right: -10, background: 'var(--accent)', color: '#fff', fontSize: 11, fontWeight: 700, padding: '2px 7px', borderRadius: 99 },
  priceBox: { background: 'var(--bg-card)', border: '1px solid var(--text-primary)', borderRadius: 12, padding: '20px 24px', marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  price:  { fontSize: 32, fontWeight: 800, color: 'var(--border)' },
  btn:    (disabled) => ({
    width: '100%',
    padding: '16px',
    background: disabled ? 'var(--text-primary)' : 'linear-gradient(90deg,var(--accent),var(--color-air))',
    border: 'none',
    borderRadius: 12,
    color: '#fff',
    fontSize: 16,
    fontWeight: 700,
    cursor: disabled ? 'not-allowed' : 'pointer',
    transition: 'opacity .15s',
  }),
  redeemBox: { background: 'var(--bg-card)', border: '1px solid var(--text-primary)', borderRadius: 12, padding: '24px', marginTop: 48 },
  input: { width: '100%', boxSizing: 'border-box', background: 'var(--bg-deeper)', border: '1px solid var(--text-primary)', borderRadius: 8, color: 'var(--border)', fontSize: 15, padding: '12px 14px', marginBottom: 12, letterSpacing: 2, textTransform: 'uppercase' },
  success: { background: 'rgba(34,197,94,0.1)', border: '1px solid var(--color-success)', borderRadius: 8, padding: '12px 16px', color: 'var(--color-success)', marginTop: 12 },
  error:   { background: 'rgba(239,68,68,0.1)', border: '1px solid var(--color-danger)', borderRadius: 8, padding: '12px 16px', color: 'var(--color-danger)', marginTop: 12 },
};

export default function GiftPage() {
  const { user, token } = useAuth();
  const navigate = useNavigate();

  const [tier, setTier]         = useState('pro');
  const [months, setMonths]     = useState(1);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  const [redeemCode, setRedeemCode]       = useState('');
  const [redeemLoading, setRedeemLoading] = useState(false);
  const [redeemMsg, setRedeemMsg]         = useState('');
  const [redeemErr, setRedeemErr]         = useState('');

  const selectedTier  = TIERS.find(t => t.id === tier);
  const selectedPrice = selectedTier?.prices[months] ?? 0;

  async function handleBuy() {
    if (!user) { navigate('/'); return; }
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/payments/gift-checkout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          tier,
          duration_months: months,
          success_url: `${window.location.origin}/gift/success`,
          cancel_url:  `${window.location.origin}/gift`,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Ошибка оплаты');
      window.location.href = data.checkout_url;
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleRedeem() {
    if (!user) { navigate('/'); return; }
    setRedeemLoading(true);
    setRedeemErr('');
    setRedeemMsg('');
    try {
      const res = await fetch(`${API_BASE}/payments/gift-redeem`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ code: redeemCode.trim().toUpperCase() }),
      });
      const data = await res.json();
      if (!res.ok) {
        const msgs = { invalid_gift_code: 'Код не найден', gift_already_redeemed: 'Код уже использован' };
        throw new Error(msgs[data.detail] || data.detail || 'Ошибка активации');
      }
      setRedeemMsg(`✅ Подписка ${data.tier.toUpperCase()} активирована на ${data.duration_months} мес.!`);
      setRedeemCode('');
    } catch (e) {
      setRedeemErr(e.message);
    } finally {
      setRedeemLoading(false);
    }
  }

  return (
    <div style={S.page}>
      <div style={S.inner}>
        <h1 style={S.h1}>🎁 Подарочная подписка</h1>
        <p style={S.sub}>Подарите близкому астрологический сервис. После оплаты вы получите код на email.</p>

        {/* Выбор тарифа */}
        <div style={S.section}>
          <div style={S.label}>Тариф</div>
          <div style={S.row}>
            {TIERS.map(t => (
              <div key={t.id} style={S.card(tier === t.id, t.color)} onClick={() => setTier(t.id)}>
                <div style={S.cardName(t.color)}>{t.name}</div>
                <div style={S.cardDesc}>{t.desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Выбор срока */}
        <div style={S.section}>
          <div style={S.label}>Срок</div>
          <div style={S.row}>
            {DURATIONS.map(d => (
              <div key={d.months} style={S.durCard(months === d.months)} onClick={() => setMonths(d.months)}>
                {d.badge && <span style={S.badge}>{d.badge}</span>}
                <div style={{ fontWeight: 700, fontSize: 15 }}>{d.label}</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
                  {selectedTier?.prices[d.months]?.toLocaleString('ru')} ₽
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Итог */}
        <div style={S.priceBox}>
          <div>
            <div style={{ color: 'var(--text-secondary)', fontSize: 14 }}>К оплате</div>
            <div style={S.price}>{selectedPrice.toLocaleString('ru')} ₽</div>
          </div>
          <div style={{ color: 'var(--text-secondary)', fontSize: 13, textAlign: 'right' }}>
            {selectedTier?.name} · {months} мес.<br/>
            Код придёт на ваш email
          </div>
        </div>

        {error && <div style={S.error}>{error}</div>}

        <button style={S.btn(loading)} onClick={handleBuy} disabled={loading}>
          {loading ? 'Переход к оплате...' : `Оплатить ${selectedPrice.toLocaleString('ru')} ₽ и получить код`}
        </button>

        {/* Блок активации */}
        <div style={S.redeemBox}>
          <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 4 }}>Есть код? Активируйте подарок</div>
          <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 16 }}>Введите полученный код ниже</div>
          <input
            style={S.input}
            placeholder="XXXXXXXXXXXXXXXX"
            value={redeemCode}
            maxLength={16}
            onChange={e => setRedeemCode(e.target.value)}
          />
          <button style={S.btn(redeemLoading || redeemCode.length < 8)} onClick={handleRedeem} disabled={redeemLoading || redeemCode.length < 8}>
            {redeemLoading ? 'Активация...' : 'Активировать'}
          </button>
          {redeemMsg && <div style={S.success}>{redeemMsg}</div>}
          {redeemErr && <div style={S.error}>{redeemErr}</div>}
        </div>
      </div>
    </div>
  );
}
