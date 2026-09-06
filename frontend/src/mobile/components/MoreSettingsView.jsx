/**
 * MoreSettingsView.jsx — «Настройки» (SPEC_MORE_SCREEN.md §6).
 *
 * Два поля с сервера: `expert_mode` и `digest_day_of_week`. ⚠️ Асимметрия
 * имён в API: GET отдаёт `digest_day_of_week`, PATCH принимает `digest_day`
 * (backend/profile/settings_router.py) — не опечатка здесь, а два разных
 * поля схемы на бэкенде.
 */

import React, { useCallback, useEffect, useState } from 'react';
import MoreCenteredNotice from './MoreCenteredNotice';
import MoreSwitch from './MoreSwitch';
import { fetchProfileSettings, updateProfileSettings } from '../lib/moreApi';

const DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

export default function MoreSettingsView() {
  const [status, setStatus] = useState('loading');
  const [settings, setSettings] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      setSettings(await fetchProfileSettings());
      setStatus('ready');
    } catch (err) {
      setError(err?.message || 'Не удалось загрузить настройки.');
      setStatus('error');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (status === 'loading') {
    return <div className="mobile-skeleton" style={{ height: 140, borderRadius: 16, background: 'var(--bg-deeper)', marginTop: 8 }} />;
  }

  if (status === 'error') {
    return <MoreCenteredNotice title="Не удалось загрузить" text={error} action="Повторить" onAction={load} />;
  }

  const toggleExpert = async () => {
    const prev = settings.expert_mode;
    setSettings({ ...settings, expert_mode: !prev });
    try {
      await updateProfileSettings({ expert_mode: !prev });
    } catch {
      setSettings({ ...settings, expert_mode: prev });
    }
  };

  const setDay = async (dayIndex) => {
    const prev = settings.digest_day_of_week;
    setSettings({ ...settings, digest_day_of_week: dayIndex });
    try {
      await updateProfileSettings({ digest_day: dayIndex });
    } catch {
      setSettings({ ...settings, digest_day_of_week: prev });
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, paddingTop: 8 }}>
      <button
        type="button"
        onClick={toggleExpert}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '13px 15px',
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 14,
          color: 'var(--text-primary)',
          fontFamily: 'var(--font-body)',
          fontSize: 14.5,
        }}
      >
        <span>Экспертный режим</span>
        <MoreSwitch on={settings.expert_mode} />
      </button>

      <div>
        <p style={{ margin: '0 0 8px', fontSize: 13, color: 'var(--text-secondary)' }}>День недельного дайджеста</p>
        <div style={{ display: 'flex', gap: 6 }}>
          {DAYS.map((label, i) => (
            <button
              key={label}
              type="button"
              onClick={() => setDay(i)}
              style={{
                flex: 1,
                height: 40,
                borderRadius: 10,
                border: `1px solid ${settings.digest_day_of_week === i ? 'var(--accent)' : 'var(--border)'}`,
                background: settings.digest_day_of_week === i ? 'var(--accent)' : 'transparent',
                color: settings.digest_day_of_week === i ? '#fff' : 'var(--text-primary)',
                fontFamily: 'var(--font-body)',
                fontSize: 12.5,
                fontWeight: 600,
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
