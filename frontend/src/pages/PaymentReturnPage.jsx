/**
 * PaymentReturnPage.jsx — куда ЮKassa возвращает после оплаты.
 *
 * До 24.09.2026 возврат вёл на /profile: ни «проверяем оплату», ни перезапроса
 * тарифа. Если вебхук опаздывал, человек видел бесплатный тариф при списанных
 * деньгах и без единого слова объяснения.
 *
 * Два случая:
 *   • `?from=app` — платили из приложения, страница открыта во внешнем
 *     браузере, где человек, скорее всего, не вошёл. Здесь ничего не
 *     проверяем: просим вернуться в приложение, там экран ожидания;
 *   • веб — номер платежа сохранён перед уходом (lib/webPayment.js), страница
 *     спрашивает `GET /payments/status/{id}` и показывает состояние. Тексты —
 *     общие с приложением (mobile/lib/paymentState.js).
 */

import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { API_BASE } from '../config';
import { authFetch } from '../api/client';
import { MAX_POLLS, POLL_MS, describePayment } from '../mobile/lib/paymentState';
import { clearWebPayment, readWebPayment } from '../lib/webPayment';

export default function PaymentReturnPage() {
  const fromApp = new URLSearchParams(useLocation().search).get('from') === 'app';
  const [pending] = useState(() => (fromApp ? null : readWebPayment()));
  const [status, setStatus] = useState(null);
  const [polls, setPolls] = useState(0);
  const [offline, setOffline] = useState(false);
  const [needLogin, setNeedLogin] = useState(false);

  const view = describePayment(status, { offline, polls, tier: pending?.tier });

  useEffect(() => {
    if (!pending?.id || view.done || needLogin) {
      if (view.done && (view.kind === 'ok' || view.kind === 'fail')) clearWebPayment();
      return undefined;
    }
    const t = setTimeout(async () => {
      try {
        const resp = await authFetch(`${API_BASE}/payments/status/${encodeURIComponent(pending.id)}`);
        if (resp.status === 401 || resp.status === 403) { setNeedLogin(true); return; }
        if (resp.ok) { setStatus(await resp.json()); setOffline(false); }
      } catch {
        setOffline(true);
      }
      setPolls((n) => n + 1);
    }, polls === 0 ? 0 : POLL_MS);
    return () => clearTimeout(t);
  }, [pending, polls, view.done, needLogin]); // eslint-disable-line react-hooks/exhaustive-deps

  let title = view.title;
  let text = view.text;
  if (fromApp) {
    title = 'Вернись в приложение';
    text = 'Оплата проверится там сама: тариф включится, как только банк подтвердит платёж. '
      + 'Эту вкладку можно закрыть.';
  } else if (!pending?.id) {
    title = 'Спасибо!';
    text = 'Если оплата прошла, тариф включится сам в течение нескольких минут — '
      + 'проверить можно в профиле.';
  } else if (needLogin) {
    title = 'Войди, чтобы увидеть статус';
    text = 'Оплата от входа не зависит: если деньги списались, тариф включится сам.';
  }

  return (
    <div className="max-w-xl mx-auto px-4 py-16 text-center">
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 700, color: 'var(--text-primary)', margin: '0 0 12px' }}>
        {title}
      </h1>
      <p style={{ fontSize: 15, lineHeight: 1.6, color: 'var(--text-secondary)', margin: '0 0 24px' }}>{text}</p>
      {!fromApp && (
        <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
          <Link to="/profile" style={{ color: 'var(--accent-fg, var(--accent))', fontWeight: 600 }}>Открыть профиль</Link>
          {(view.kind === 'later' || polls >= MAX_POLLS) && ' · если деньги списались, а тарифа нет, напиши в поддержку из профиля'}
        </p>
      )}
    </div>
  );
}
