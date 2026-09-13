/**
 * MoreNotificationsView.jsx — «Уведомления» (SPEC_MORE_SCREEN.md §7).
 *
 * Экран сводит ДВА разных механизма, и их не надо путать:
 *
 * 1. **Тумблер «Уведомления на этом устройстве»** — локальные уведомления
 *    Android (`@capacitor/local-notifications`). Их планирует само приложение
 *    из выдачи `GET /push/upcoming`, поэтому они работают и без сети в момент
 *    показа. Только в приложении; в вебе этого тумблера нет вовсе.
 * 2. **Тумблеры видов событий, время и тихие часы** — НАСТРОЙКИ НА СЕРВЕРЕ
 *    (`/push/settings`), общие с сайтом. Они определяют, что попадёт в выдачу,
 *    то есть управляют обоими механизмами сразу — и веб-пушами, и локальными
 *    уведомлениями.
 *
 * ⚠️ Поэтому серверные настройки БОЛЬШЕ НЕ СПРЯТАНЫ за проверкой Web Push.
 * До 13.09.2026 весь экран закрывался условием «есть serviceWorker +
 * PushManager + Notification», и в Android WebView, где PushManager может
 * отсутствовать, человек видел бы «недоступно» — включая настройки, от Web
 * Push никак не зависящие. Проверка осталась ровно там, где она про дело: в
 * подписи о том, куда приходят уведомления в вебе.
 */

import React, { useCallback, useEffect, useState } from 'react';
import MoreCenteredNotice from './MoreCenteredNotice';
import MoreNotificationsDebug from './MoreNotificationsDebug'; // ОТЛАДКА: снять перед вливанием в main
import MoreSwitch from './MoreSwitch';
import { fetchPushSettings, updatePushSettings } from '../lib/moreApi';
import {
  LOCAL_NOTIFICATIONS_SUPPORTED,
  cancelOwnedPlan,
  permissionState,
  requestPermission,
} from '../lib/localNotifications';
import {
  localNotificationsEnabled,
  setLocalNotificationsEnabled,
  syncLocalNotifications,
} from '../lib/localNotificationsSync';

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

function ToggleRow({ label, hint, on, onToggle }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      style={{
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        padding: '13px 15px',
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 14,
        color: 'var(--text-primary)',
        fontFamily: 'var(--font-body)',
        fontSize: 14.5,
        textAlign: 'left',
      }}
    >
      <span>
        {label}
        {hint ? (
          <span style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
            {hint}
          </span>
        ) : null}
      </span>
      <MoreSwitch on={on} />
    </button>
  );
}

/**
 * Экран-предисловие перед системным диалогом.
 *
 * ⚠️ Это не украшение и не «хорошая практика вообще»: на Android отказ в
 * системном диалоге ОКОНЧАТЕЛЕН — обычными средствами человек его не вернёт,
 * только через настройки приложения, куда никто не идёт. То есть один вопрос,
 * заданный не вовремя и без объяснения, закрывает канал навсегда. Ровно по
 * этой причине 10.09.2026 из ChartPage убрали автоматический вызов
 * `enablePush` через 5 секунд после открытия карты (docs/HISTORY-push.md).
 *
 * Поэтому диалог вызывается ТОЛЬКО отсюда, только после тапа на тумблер и
 * только по кнопке «Разрешить». Кнопка «Не сейчас» ничего не спрашивает и
 * ничего не запоминает — спросить можно будет ещё раз, потому что системного
 * вопроса не было.
 */
function PermissionIntro({ onAllow, onCancel, busy }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        padding: 16,
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 14,
        marginTop: 8,
      }}
    >
      <div style={{ fontFamily: 'var(--font-display)', fontSize: 17, color: 'var(--text-primary)' }}>
        Уведомления по вашей карте
      </div>
      <div style={{ fontSize: 13.5, lineHeight: 1.5, color: 'var(--text-secondary)' }}>
        Приложение напомнит о важных транзитах, подходящих днях из планера и фазах Луны —
        одним уведомлением в день, в выбранное вами время. Что именно приходит, вы настроите
        ниже, и отключить можно в любой момент.
      </div>
      <div style={{ fontSize: 13.5, lineHeight: 1.5, color: 'var(--text-secondary)' }}>
        Дальше Android спросит разрешение. Если отказать, вернуть его получится только через
        настройки телефона.
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
        <button
          type="button"
          onClick={onAllow}
          disabled={busy}
          style={{
            flex: 1,
            padding: '12px 14px',
            borderRadius: 12,
            border: 'none',
            background: 'var(--accent)',
            color: '#ffffff',
            fontFamily: 'var(--font-body)',
            fontSize: 14.5,
            opacity: busy ? 0.6 : 1,
          }}
        >
          Разрешить
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          style={{
            flex: 1,
            padding: '12px 14px',
            borderRadius: 12,
            border: '1px solid var(--border)',
            background: 'transparent',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-body)',
            fontSize: 14.5,
          }}
        >
          Не сейчас
        </button>
      </div>
    </div>
  );
}

/** Локальные уведомления: тумблер + предисловие + честный текст про отказ. */
function LocalNotificationsBlock() {
  const [on, setOn] = useState(localNotificationsEnabled());
  const [intro, setIntro] = useState(false);
  const [busy, setBusy] = useState(false);
  const [denied, setDenied] = useState(false);

  // Разрешение могли отозвать в настройках телефона, пока приложение не
  // работало. Тумблер обязан показывать положение дел, а не своё воспоминание
  // о нём: иначе он стоит «включено», а в шторке ничего не появляется.
  useEffect(() => {
    let alive = true;
    if (!localNotificationsEnabled()) return undefined;
    permissionState().then((state) => {
      if (!alive) return;
      if (state !== 'granted') {
        setLocalNotificationsEnabled(false);
        setOn(false);
        setDenied(state === 'denied');
      }
    });
    return () => { alive = false; };
  }, []);

  async function enable() {
    setBusy(true);
    const state = await requestPermission();
    setBusy(false);
    setIntro(false);
    if (state !== 'granted') {
      setDenied(state === 'denied');
      return;
    }
    setDenied(false);
    setLocalNotificationsEnabled(true);
    setOn(true);
    syncLocalNotifications();
  }

  async function handleToggle() {
    if (on) {
      setLocalNotificationsEnabled(false);
      setOn(false);
      // Снимается ПЛАН, а не всё подряд: пересборка и выключение трогают ровно
      // своё множество id (localNotifications.js). Проверочное уведомление из
      // отладочной панели планом не является и здесь не отменяется.
      await cancelOwnedPlan();
      return;
    }
    // Разрешение уже есть — второй раз спрашивать нечего и незачем.
    if ((await permissionState()) === 'granted') {
      setDenied(false);
      setLocalNotificationsEnabled(true);
      setOn(true);
      syncLocalNotifications();
      return;
    }
    setIntro(true);
  }

  return (
    <>
      <ToggleRow
        label="Уведомления на этом устройстве"
        hint="Приложение напомнит о событиях по вашей карте"
        on={on}
        onToggle={handleToggle}
      />
      {intro ? <PermissionIntro onAllow={enable} onCancel={() => setIntro(false)} busy={busy} /> : null}
      {denied && !intro ? (
        <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--text-secondary)' }}>
          Уведомления запрещены в настройках телефона. Включить их можно только там:
          «Настройки → Приложения → Aristea → Уведомления».
        </p>
      ) : null}
    </>
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

  useEffect(() => { load(); }, [load]);

  if (!PUSH_SUPPORTED && !LOCAL_NOTIFICATIONS_SUPPORTED) {
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
      // Состав уведомлений изменился — план на устройстве обязан пересобраться
      // сразу, а не при следующем заходе: иначе выключенный вид событий ещё
      // неделю приходил бы по уже поставленному плану.
      syncLocalNotifications();
    } catch {
      setSettings(settings); // откат конкретного тумблера при неудаче
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 8 }}>
      {LOCAL_NOTIFICATIONS_SUPPORTED ? <LocalNotificationsBlock /> : null}
      {TOGGLES.map(({ key, label }) => (
        <ToggleRow key={key} label={label} on={settings[key]} onToggle={() => toggle(key)} />
      ))}
      <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--text-secondary)' }}>
        Уведомления приходят с {settings.daily_time} до {settings.quiet_from || '22:00'}
      </p>
      <MoreNotificationsDebug settings={settings} />{/* ОТЛАДКА: снять перед вливанием в main */}
    </div>
  );
}
