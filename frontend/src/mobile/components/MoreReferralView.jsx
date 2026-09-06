/**
 * MoreReferralView.jsx — «Друзья» (SPEC_MORE_SCREEN.md §6.1).
 *
 * Ссылка копируется в буфер обмена (`navigator.clipboard.writeText`), не
 * системным шерингом — решение по инфраструктуре: `@capacitor/share` не
 * ставим, один плагин (`@capacitor/browser`) закрывает остальные нужды
 * экрана (§4.3, §6.2).
 */

import React, { useCallback, useEffect, useState } from 'react';
import MoreCenteredNotice from './MoreCenteredNotice';
import { fetchReferral } from '../lib/moreApi';

export default function MoreReferralView() {
  const [status, setStatus] = useState('loading');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      setData(await fetchReferral());
      setStatus('ready');
    } catch (err) {
      setError(err?.message || 'Не удалось загрузить реферальную ссылку.');
      setStatus('error');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const copy = useCallback(async () => {
    if (!data?.ref_url) return;
    try {
      await navigator.clipboard.writeText(data.ref_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Буфер обмена недоступен (см. SPEC_MORE_SCREEN.md §10, проверка на
      // устройстве) — молча не показываем «скопировано», раз не скопировали.
    }
  }, [data]);

  if (status === 'loading') {
    return <div className="mobile-skeleton" style={{ height: 140, borderRadius: 16, background: 'var(--bg-deeper)', marginTop: 8 }} />;
  }

  if (status === 'error') {
    return <MoreCenteredNotice title="Не удалось загрузить" text={error} action="Повторить" onAction={load} />;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, paddingTop: 8 }}>
      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 16, padding: '16px' }}>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>Ваша ссылка</p>
        <p style={{ margin: '4px 0 0', fontFamily: 'var(--font-body)', fontSize: 14, wordBreak: 'break-all', color: 'var(--text-primary)' }}>
          {data.ref_url}
        </p>
        <button type="button" className="mobile-btn-primary" style={{ height: 44, fontSize: 14, marginTop: 12 }} onClick={copy}>
          {copied ? 'Скопировано' : 'Копировать ссылку'}
        </button>
      </div>

      <div style={{ display: 'flex', gap: 12 }}>
        <div style={{ flex: 1, background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 14, padding: '12px 14px', textAlign: 'center' }}>
          <p style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>
            {data.referrals_count}
          </p>
          <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-secondary)' }}>приглашено</p>
        </div>
        <div style={{ flex: 1, background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 14, padding: '12px 14px', textAlign: 'center' }}>
          <p style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>
            {data.reward_weeks_earned}
          </p>
          <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-secondary)' }}>недель награды</p>
        </div>
      </div>
    </div>
  );
}
