/**
 * PaySheet.jsx — оплата тарифа из приложения и экран ожидания.
 *
 * Два режима:
 *   • choose — Вега и Лира (только то, что старше текущего тарифа), кнопка
 *     «Оплатить». Платёж создаёт приложение само (lib/payApi.js), страница
 *     ЮKassa открывается во внешнем браузере;
 *   • status — «Проверяем оплату…» после возврата из браузера. Спрашивает
 *     `GET /payments/status/{id}` раз в POLL_MS, пока приложение на экране.
 *     Тексты — lib/paymentState.js.
 *
 * Ожидающий платёж хранится на устройстве (`readPending`), поэтому экран
 * ожидания открывается сам при каждом возврате в приложение, пока платёж не
 * решён, — даже если система выгрузила приложение, пока человек платил.
 *
 * ⚠️ Без сети экран не ошибка, а «проверим, когда связь вернётся»: деньги
 * при этом могли уйти, и красная ошибка в этот момент — худшее, что можно
 * показать. Тариф в любом случае включат вебхук или ежедневная сверка.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { TIERS, TIER_NAMES, tierFeatures, tierPriceLabel } from '../../constants';
import { openInBrowser } from '../lib/openInBrowser';
import { onPaySheet } from '../lib/paySheetBus';
import {
  clearPending, createAppCheckout, fetchPaymentStatus, readPending, rememberPending,
} from '../lib/payApi';
import { MAX_POLLS, POLL_MS, describePayment } from '../lib/paymentState';
import { getSubscription } from '../lib/tierSource';
import { isConnectivity, errorText } from '../lib/netError';
import useTier from '../lib/useTier';
import AnnouncementBanner from '../../components/AnnouncementBanner';

const SELLABLE = ['lite', 'pro'];

function rank(tier) {
  return TIERS.findIndex((t) => t.id === tier);
}

export default function PaySheet() {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState('choose');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState(null);
  const [offline, setOffline] = useState(false);
  const [polls, setPolls] = useState(0);
  const { tier } = useTier();
  const timer = useRef(null);
  const pending = useRef(null);

  const stop = () => { if (timer.current) clearTimeout(timer.current); timer.current = null; };

  const showStatus = useCallback(() => {
    pending.current = readPending();
    if (!pending.current) return;
    setMode('status'); setStatus(null); setOffline(false); setPolls(0); setOpen(true);
  }, []);

  useEffect(() => onPaySheet(({ mode: m }) => {
    setError('');
    if (m === 'status') { showStatus(); return; }
    setMode('choose'); setOpen(true);
  }), [showStatus]);

  // Возврат из браузера ЮKassa и холодный старт после выгрузки системой.
  useEffect(() => {
    const onVisible = () => { if (document.visibilityState === 'visible') showStatus(); };
    showStatus();
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [showStatus]);

  // Опрос статуса, пока экран ожидания открыт и приложение видно.
  useEffect(() => {
    if (!open || mode !== 'status' || !pending.current) return undefined;
    const view = describePayment(status, { offline, polls, tier: pending.current.tier });
    if (view.done) {
      // «Банк ещё не подтвердил» платёж НЕ забывает — проверим при следующем
      // возврате в приложение. Остальные исходы окончательные.
      if (!(view.kind === 'later' && status?.state !== 'review')) clearPending();
      if (view.kind === 'ok') getSubscription({ force: true }).catch(() => {});
      return undefined;
    }
    timer.current = setTimeout(async () => {
      if (document.visibilityState !== 'visible') return;
      try {
        setStatus(await fetchPaymentStatus(pending.current.id));
        setOffline(false);
      } catch (err) {
        setOffline(isConnectivity(err));
      }
      setPolls((n) => n + 1);
    }, status === null && polls === 0 ? 0 : POLL_MS);
    return stop;
  }, [open, mode, status, offline, polls]);

  const pay = async (id) => {
    setBusy(true); setError('');
    try {
      const { checkout_url: url, payment_id: pid } = await createAppCheckout(id);
      if (!url || !pid) throw new Error('Платёжный сервис вернул неожиданный ответ.');
      rememberPending(pid, id);
      pending.current = readPending();
      setMode('status'); setStatus(null); setPolls(0); setOffline(false);
      await openInBrowser(url);
    } catch (err) {
      setError(errorText(err, 'Не удалось начать оплату.', { write: true }));
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;
  const close = () => { stop(); setOpen(false); };
  const view = mode === 'status'
    ? describePayment(status, { offline, polls, tier: pending.current?.tier })
    : null;
  const offers = SELLABLE.filter((id) => rank(id) > rank(tier || 'free'));

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={close}
      style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'flex-end' }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%', maxHeight: '85%', overflowY: 'auto', background: 'var(--bg-page)',
          borderRadius: 'var(--radius-lg) var(--radius-lg) 0 0',
          padding: '18px 16px calc(18px + env(safe-area-inset-bottom))',
          display: 'flex', flexDirection: 'column', gap: 12,
        }}
      >
        {mode === 'choose' && (
          <>
            <p style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
              Тарифы
            </p>
            <AnnouncementBanner />
            {offers.length === 0 && (
              <p style={{ margin: 0, fontSize: 14, color: 'var(--text-secondary)' }}>
                У тебя уже старший из доступных тарифов.
              </p>
            )}
            {offers.map((id) => (
              <section key={id} style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                <p style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
                  {TIER_NAMES[id]} · {tierPriceLabel(id)} в месяц
                </p>
                <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {tierFeatures(id, 4).map((f) => (
                    <li key={f} style={{ fontSize: 13, lineHeight: 1.4, color: 'var(--text-secondary)' }}>· {f}</li>
                  ))}
                </ul>
                <button type="button" className="mobile-btn-primary" disabled={busy} style={{ height: 44, fontSize: 14 }} onClick={() => pay(id)}>
                  {busy ? 'Открываем оплату…' : `Оплатить ${tierPriceLabel(id)}`}
                </button>
              </section>
            ))}
            <p style={{ margin: 0, fontSize: 12, lineHeight: 1.5, color: 'var(--text-secondary)' }}>
              Оплата разовая, за 30 дней, без автопродления. Откроется страница ЮKassa в браузере —
              после оплаты вернись в приложение, тариф включится сам.
            </p>
            {error && <p role="alert" style={{ margin: 0, fontSize: 13, color: 'var(--color-danger)' }}>{error}</p>}
          </>
        )}

        {mode === 'status' && view && (
          <>
            <p style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
              {view.title}
            </p>
            <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: 'var(--text-secondary)' }}>{view.text}</p>
            {view.kind === 'later' && (
              <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5, color: 'var(--text-secondary)' }}>
                Написать в поддержку: «Ещё» → «Оплата и поддержка».
              </p>
            )}
            {view.kind === 'fail' && (
              <button type="button" className="mobile-btn-primary" style={{ height: 44, fontSize: 14 }} onClick={() => setMode('choose')}>
                Попробовать ещё раз
              </button>
            )}
          </>
        )}

        <button type="button" className="mobile-link" onClick={close} style={{ alignSelf: 'center' }}>
          {mode === 'status' && view && !view.done ? 'Свернуть — проверим сами' : 'Закрыть'}
        </button>
      </div>
    </div>
  );
}
