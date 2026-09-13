/**
 * MoreDeviceChannel.jsx — тумблер «Уведомления на этом устройстве».
 *
 * Отдельный файл, а не код внутри `MoreNotificationsView`, по двум причинам:
 *
 * 1. ⚠️ Ветка `local-notifications` добавляет на ТОТ ЖЕ экран тумблер с тем же
 *    смыслом. Держи это в общем файле — при слиянии пришлось бы разбирать
 *    конфликт посреди чужой вёрстки. Здесь вставка в общий экран занимает две
 *    строки, а объединение двух каналов сведётся к правке одного обработчика
 *    в этом файле.
 * 2. Экран настроек — про серверные настройки, общие с сайтом. Канал доставки
 *    к ним не относится: он про это устройство и только про него.
 *
 * ⚠️ Разрешение спрашивается ТОЛЬКО по тапу и ТОЛЬКО после предисловия. На
 * Android отказ в системном диалоге окончателен: обычными средствами человек
 * его не вернёт, то есть один вопрос в неудачный момент закрывает канал
 * навсегда. Ровно по этой причине 10.09.2026 из ChartPage убрали
 * автоматический вызов `enablePush` через 5 секунд после открытия карты
 * (docs/HISTORY-push.md).
 *
 * ⚠️ Что здесь ЕЩЁ НЕ сделано и почему это не забывчивость: при слиянии с
 * `local-notifications` сюда добавляется вторая половина решения — неудачная
 * регистрация (нет сервисов Google) должна включать локальные уведомления
 * запасным каналом, а удачная — снимать их. Кода локальных уведомлений на
 * этой ветке нет вовсе, поэтому здесь только серверный канал, а место для
 * развилки отмечено ниже.
 */

import React, { useCallback, useEffect, useState } from 'react';
import MoreSwitch from './MoreSwitch';
import {
  DEVICE_PUSH_SUPPORTED,
  currentDeviceToken,
  registerDevice,
  unregisterDevice,
} from '../lib/devicePush';

/** Намерение человека — отдельно от системного разрешения и от наличия токена. */
const ENABLED_KEY = 'aristea_device_push';

export function devicePushEnabled() {
  try {
    return localStorage.getItem(ENABLED_KEY) === '1';
  } catch {
    return false;
  }
}

function setEnabled(on) {
  try {
    localStorage.setItem(ENABLED_KEY, on ? '1' : '0');
  } catch {
    /* приватный режим webview — тумблер просто не запомнится */
  }
}

const row = {
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
};

const hint = { display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 };
const note = { margin: '4px 0 0', fontSize: 12, color: 'var(--text-secondary)' };

function Intro({ onAllow, onCancel, busy }) {
  return (
    <div
      style={{
        display: 'flex', flexDirection: 'column', gap: 12, padding: 16,
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 14, marginTop: 8,
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
          type="button" onClick={onAllow} disabled={busy}
          style={{
            flex: 1, padding: '12px 14px', borderRadius: 12, border: 'none',
            background: 'var(--accent)', color: '#ffffff',
            fontFamily: 'var(--font-body)', fontSize: 14.5, opacity: busy ? 0.6 : 1,
          }}
        >
          Разрешить
        </button>
        <button
          type="button" onClick={onCancel} disabled={busy}
          style={{
            flex: 1, padding: '12px 14px', borderRadius: 12,
            border: '1px solid var(--border)', background: 'transparent',
            color: 'var(--text-primary)', fontFamily: 'var(--font-body)', fontSize: 14.5,
          }}
        >
          Не сейчас
        </button>
      </div>
    </div>
  );
}

export default function MoreDeviceChannel() {
  const [on, setOn] = useState(devicePushEnabled());
  const [intro, setIntro] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');

  // Токен мог протухнуть или быть отозван, пока приложение не работало.
  // Перерегистрация при открытии экрана — самый дешёвый момент это заметить.
  const refresh = useCallback(async () => {
    if (!devicePushEnabled()) return;
    const token = await registerDevice();
    if (!token) {
      setProblem('device');
      setOn(false);
      setEnabled(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function enable() {
    setBusy(true);
    const token = await registerDevice();
    setBusy(false);
    setIntro(false);

    if (!token) {
      // ⚠️ Сюда же приходит устройство БЕЗ сервисов Google: у него регистрация
      // не удастся никогда. При слиянии с `local-notifications` в этой ветке
      // включается запасной канал — локальные уведомления.
      setProblem('device');
      return;
    }
    setProblem('');
    setEnabled(true);
    setOn(true);
  }

  async function toggle() {
    if (on) {
      setEnabled(false);
      setOn(false);
      await unregisterDevice();
      return;
    }
    // Токен уже есть — второй раз спрашивать нечего.
    if (currentDeviceToken()) {
      setEnabled(true);
      setOn(true);
      return;
    }
    setIntro(true);
  }

  if (!DEVICE_PUSH_SUPPORTED) return null;

  return (
    <>
      <button type="button" onClick={toggle} style={row}>
        <span>
          Уведомления на этом устройстве
          <span style={hint}>Приходят, даже когда приложение закрыто</span>
        </span>
        <MoreSwitch on={on} />
      </button>

      {intro ? <Intro onAllow={enable} onCancel={() => setIntro(false)} busy={busy} /> : null}

      {problem === 'device' && !intro ? (
        <p style={note}>
          Не удалось подключить уведомления на этом устройстве. Проверьте, что уведомления
          разрешены приложению в настройках телефона.
        </p>
      ) : null}
    </>
  );
}
