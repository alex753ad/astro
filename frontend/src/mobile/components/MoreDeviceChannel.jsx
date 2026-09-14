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
 * ⚠️ ЗДЕСЬ ЖЕ ВЫБИРАЕТСЯ КАНАЛ, и в этом весь дедуп между ними.
 *
 * Каналов два, и они решают одну задачу разными средствами:
 *   • серверный пуш (FCM) — будит устройство, но требует сервисов Google;
 *   • локальные уведомления — работают везде, но НЕ будят телефон: без
 *     разрешения на точный будильник Android ставит неточный, и тот ждёт, пока
 *     человек сам возьмёт телефон (docs/HISTORY-push.md).
 *
 * Правило простое: получили токен FCM — работаем им и локальных не планируем,
 * а уже поставленные снимаем. Не получили (нет сервисов Google, отказ моста) —
 * включаем локальные запасным каналом.
 *
 * ⚠️ Оба конца опираются на ОДИН И ТОТ ЖЕ факт — «токен есть». Сервер шлёт
 * FCM, потому что у пользователя есть запись в `device_tokens`; устройство не
 * планирует локальных, потому что токен у него на руках. Разъехаться им негде,
 * и поэтому один и тот же `key` не может прийти дважды. Серверный вариант
 * («пусть `/push/upcoming` отдаёт пустую выдачу, когда токен есть») рассмотрен
 * и отклонён решением владельца: он лишает устройство запасного канала в
 * случае, когда доставка молча сломается.
 */

import React, { useCallback, useEffect, useState } from 'react';
import MoreSwitch from './MoreSwitch';
import {
  DEVICE_PUSH_SUPPORTED,
  currentDeviceToken,
  registerDevice,
  unregisterDevice,
} from '../lib/devicePush';
import { cancelOwnedPlan, permissionState } from '../lib/localNotifications';
import { CHANNEL_DEVICE, CHANNEL_SERVER, decideChannel } from '../lib/channelChoice';
import {
  setLocalNotificationsEnabled,
  syncLocalNotifications,
} from '../lib/localNotificationsSync';

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
  borderRadius: 'var(--radius-lg)',
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
        borderRadius: 'var(--radius-lg)', marginTop: 8,
      }}
    >
      <div style={{ fontFamily: 'var(--font-display)', fontSize: 17, color: 'var(--text-primary)' }}>
        Уведомления по вашей карте
      </div>
      <div style={{ fontSize: 13.5, lineHeight: 1.5, color: 'var(--text-secondary)' }}>
        Приложение напомнит о важных транзитах, подходящих днях из планера и фазах Луны —
        одним уведомлением в день, начиная с выбранного вами времени. Что именно приходит, вы настроите
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
            flex: 1, padding: '12px 14px', borderRadius: 'var(--radius-md)', border: 'none',
            background: 'var(--accent)', color: '#ffffff',
            fontFamily: 'var(--font-body)', fontSize: 14.5, opacity: busy ? 0.6 : 1,
          }}
        >
          Разрешить
        </button>
        <button
          type="button" onClick={onCancel} disabled={busy}
          style={{
            flex: 1, padding: '12px 14px', borderRadius: 'var(--radius-md)',
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
  // Каким каналом работаем: 'server' (FCM) или 'device' (локальные). Хранится
  // ради подписи под тумблером — человек должен понимать, почему у него
  // уведомления приходят иначе, чем обещано, а не гадать.
  const [channel, setChannel] = useState(null);

  /**
   * Включить канал: сначала серверный, при неудаче — локальный.
   *
   * ⚠️ Порядок обязателен и не взаимозаменяем. Серверный будит устройство,
   * локальный нет; выбрать локальный там, где работает серверный, значит
   * сознательно отдать человеку худший канал. Поэтому локальный включается
   * ТОЛЬКО как ответ на неудачу регистрации.
   */
  const chooseChannel = useCallback(async () => {
    const token = await registerDevice();
    // ⚠️ Решение — в `channelChoice.js`, отдельной чистой функцией, и это не
    // церемония: инвариант «активен ровно один канал» внутри обработчика
    // нечем закрепить, кроме рендера, а цена его нарушения — дубли в шторке.
    // Здесь остаются только последствия решения.
    const chosen = decideChannel(token, await permissionState());

    if (chosen === CHANNEL_SERVER) {
      // Серверный канал работает. Локальные обязаны замолчать — иначе одно и
      // то же событие придёт дважды: пушем и своим уведомлением.
      setLocalNotificationsEnabled(false);
      await cancelOwnedPlan();
      return chosen;
    }

    if (chosen === CHANNEL_DEVICE) {
      // ⚠️ Сюда приходит устройство БЕЗ сервисов Google: у него регистрация не
      // удастся никогда, и локальные уведомления — единственное, что у него
      // вообще может работать. Разрешение уже выдано (его спрашивает
      // registerDevice до обращения к серверу), второй раз не спрашиваем.
      setLocalNotificationsEnabled(true);
      await syncLocalNotifications();
      return chosen;
    }
    return null;
  }, []);

  // Токен мог протухнуть или быть отозван, пока приложение не работало.
  // Перерегистрация при открытии экрана — самый дешёвый момент это заметить,
  // и заодно момент, когда канал может смениться в обе стороны.
  const refresh = useCallback(async () => {
    if (!devicePushEnabled()) return;
    const chosen = await chooseChannel();
    if (!chosen) {
      setProblem('none');
      setOn(false);
      setEnabled(false);
      return;
    }
    setChannel(chosen);
  }, [chooseChannel]);

  useEffect(() => { refresh(); }, [refresh]);

  async function enable() {
    setBusy(true);
    const chosen = await chooseChannel();
    setBusy(false);
    setIntro(false);

    if (!chosen) {
      setProblem('none');
      return;
    }
    setProblem('');
    setChannel(chosen);
    setEnabled(true);
    setOn(true);
  }

  async function toggle() {
    if (on) {
      setEnabled(false);
      setOn(false);
      // Гасим ОБА канала: какой из них был активен, человека не касается —
      // он выключил уведомления, а не «серверные уведомления».
      setLocalNotificationsEnabled(false);
      await Promise.all([unregisterDevice(), cancelOwnedPlan()]);
      setChannel(null);
      return;
    }
    // Токен уже есть — второй раз разрешение не спрашиваем.
    if (currentDeviceToken()) {
      setLocalNotificationsEnabled(false);
      await cancelOwnedPlan();
      setChannel('server');
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

      {on && channel === 'device' ? (
        <p style={note}>
          На этом телефоне уведомления работают в упрощённом режиме: они появятся, когда вы
          возьмёте телефон в руки, а не в тот же момент. Так бывает на устройствах без
          сервисов Google.
        </p>
      ) : null}

      {problem === 'none' && !intro ? (
        <p style={note}>
          Не удалось включить уведомления на этом устройстве. Проверьте, что уведомления
          разрешены приложению в настройках телефона.
        </p>
      ) : null}
    </>
  );
}
