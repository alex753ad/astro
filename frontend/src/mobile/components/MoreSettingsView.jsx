/**
 * MoreSettingsView.jsx — «Настройки» (SPEC_MORE_SCREEN.md §6).
 *
 * Поле с сервера одно — `digest_day_of_week`. ⚠️ Асимметрия имён в API: GET
 * отдаёт `digest_day_of_week`, PATCH принимает `digest_day`
 * (backend/profile/settings_router.py) — не опечатка здесь, а два разных
 * поля схемы на бэкенде.
 *
 * ⚠️ Переключателя «Экспертный режим» здесь нет намеренно (решение владельца
 * 27.09.2026): поле `expert_mode` на сервере есть, но его не читал никто —
 * ни приложение, ни веб, то есть переключатель ничего не делал. Поле
 * оставлено; «сделать или удалить» — пункт TASKS.md. Не возвращать
 * переключатель, пока у флага нет потребителя.
 *
 * День дайджеста виден только на Лире и Орионе (lib/digestAccess.js).
 */

import React, { useCallback, useEffect, useState } from 'react';
import MoreCenteredNotice from './MoreCenteredNotice';
import { fetchProfileSettings, updateProfileSettings } from '../lib/moreApi';
import { appVersionShort } from '../lib/supportContext';
import { showsDigestDay } from '../lib/digestAccess';

const DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

// Версия видна и при отказе загрузки настроек: её спрашивают именно тогда,
// когда что-то не работает. Здесь — без хеша сборки; с хешем она уходит с
// обращением в поддержку (appVersionLabel).
const VERSION = (
  <p style={{ margin: '8px 0 0', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center' }}>
    Версия {appVersionShort()}
  </p>
);

export default function MoreSettingsView({ tier }) {
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
    return <div className="mobile-skeleton" style={{ height: 140, borderRadius: 'var(--radius-lg)', background: 'var(--bg-deeper)', marginTop: 8 }} />;
  }

  if (status === 'error') {
    return <><MoreCenteredNotice title="Не удалось загрузить" text={error} action="Повторить" onAction={load} support="more-settings" />{VERSION}</>;
  }

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
      {showsDigestDay(tier) && (
      <div>
        <p style={{ margin: '0 0 2px', fontSize: 13, color: 'var(--text-primary)' }}>День недельного дайджеста</p>
        <p style={{ margin: '0 0 8px', fontSize: 12, lineHeight: 1.45, color: 'var(--text-secondary)' }}>
          Раз в неделю в этот день пришлём на почту главные события недели по твоей карте
        </p>
        <div style={{ display: 'flex', gap: 6 }}>
          {DAYS.map((label, i) => (
            <button
              key={label}
              type="button"
              onClick={() => setDay(i)}
              style={{
                flex: 1,
                height: 40,
                borderRadius: 'var(--radius-md)',
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
      )}
      {VERSION}
    </div>
  );
}
