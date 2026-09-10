/**
 * MoreNotificationsView.jsx — «Уведомления» (SPEC_MORE_SCREEN.md §7).
 *
 * ⚠️ Работает ли Web Push (`navigator.serviceWorker` + `PushManager` +
 * `Notification`) внутри Android WebView Capacitor — не проверено разведкой
 * и не проверяется без устройства (MORE_API_RECON.md §3). Если хоть один
 * из трёх API отсутствует — состояние «недоступно», а не рабочие на вид
 * тумблеры, которые сохраняются на сервере, но никогда не приводят к
 * уведомлению: это хуже честного отказа, человек будет уверен, что
 * подписался.
 */

import React, { useCallback, useEffect, useState } from 'react';
import MoreCenteredNotice from './MoreCenteredNotice';
import MoreSwitch from './MoreSwitch';
import { fetchPushSettings, updatePushSettings } from '../lib/moreApi';

const PUSH_SUPPORTED =
  typeof navigator !== 'undefined' &&
  'serviceWorker' in navigator &&
  typeof window !== 'undefined' &&
  'PushManager' in window &&
  'Notification' in window;

const TOGGLES = [
  { key: 'daily_forecast', label: 'Прогноз дня' },
  { key: 'planner', label: 'Планер' },
  { key: 'key_transits', label: 'Важные транзиты' },
  { key: 'moon_phases', label: 'Фазы Луны' },
];

function ToggleRow({ label, on, onToggle }) {
  return (
    <button
      type="button"
      onClick={onToggle}
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
      <span>{label}</span>
      <MoreSwitch on={on} />
    </button>
  );
}

export default function MoreNotificationsView() {
  const [status, setStatus] = useState('loading');
  const [settings, setSettings] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      setSettings(await fetchPushSettings());
      setStatus('ready');
    } catch (err) {
      setError(err?.message || 'Не удалось загрузить настройки уведомлений.');
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    if (PUSH_SUPPORTED) load();
  }, [load]);

  if (!PUSH_SUPPORTED) {
    return <MoreCenteredNotice title="Push-уведомления недоступны на этом устройстве" />;
  }

  if (status === 'loading') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 8 }}>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="mobile-skeleton" style={{ height: 48, borderRadius: 14, background: 'var(--bg-deeper)' }} />
        ))}
      </div>
    );
  }

  if (status === 'error') {
    return <MoreCenteredNotice title="Не удалось загрузить" text={error} action="Повторить" onAction={load} />;
  }

  const toggle = async (key) => {
    const next = { ...settings, [key]: !settings[key] };
    setSettings(next); // оптимистично — своя ошибка не должна откатывать весь экран в скелет
    try {
      await updatePushSettings({ [key]: next[key] });
    } catch {
      setSettings(settings); // откат конкретного тумблера при неудаче
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 8 }}>
      {TOGGLES.map(({ key, label }) => (
        <ToggleRow key={key} label={label} on={settings[key]} onToggle={() => toggle(key)} />
      ))}
      <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--text-secondary)' }}>
        Уведомления приходят с {settings.daily_time} до {settings.quiet_from || '22:00'}
      </p>
      {/* ⚠️ Честная строка про то, что эти тумблеры делают СЕГОДНЯ.
          Экран сохраняет настройки на сервер, но приложение не создаёт
          push-подписку нигде и никогда: ни `enablePush`, ни `pushManager`
          в mobile/ не вызываются (проверено грепом 10.09.2026). То есть сами
          уведомления по этим настройкам приходят в браузер, а не сюда.
          Без этой строки тумблеры выглядят рабочими и человек уверен, что
          подписался, — ровно то, о чём предупреждает докстринг файла. */}
      <p style={{ margin: '10px 0 0', fontSize: 12, color: 'var(--text-secondary)' }}>
        Настройки общие с сайтом — уведомления приходят туда.
      </p>
    </div>
  );
}
