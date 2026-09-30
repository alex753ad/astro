/**
 * PushNudge.jsx — зовём включить уведомления (решение владельца 30.09.2026).
 * Кому и что показывать, решает lib/pushNudge.js (`decideNudge`, с тестом);
 * здесь — только показ и последствия ответа.
 *
 * ⚠️ Решение принимается при открытии ленты и при возврате в приложение, но
 * НЕ в момент первого прогноза: отметку `forecastSeen` ставит карточка
 * прогноза уже после загрузки, так что экран появляется при первом возврате
 * в ленту (другая вкладка, свёрнутое приложение) — не поверх прогноза,
 * который человек ещё читает.
 *
 * ⚠️ Системный диалог — ТОЛЬКО по нажатию «Включить». Отказ на Android 13+
 * со второго раза окончателен (шапка MoreDeviceChannel.jsx); дальше помогают
 * только настройки телефона — отсюда кнопка «Открыть настройки».
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { deviceChoice, enableDeviceChannel } from '../lib/deviceChannel';
import { permissionState } from '../lib/localNotifications';
import {
  NUDGE_CARD, NUDGE_CARD_SETTINGS, NUDGE_SCREEN, NUDGE_SILENT, NUDGE_WAIT,
  decideNudge, readNudge, writeNudge,
} from '../lib/pushNudge';

async function openNotificationSettings() {
  try {
    // Объект плагина не await-им и не возвращаем (frontend/src/mobile/CLAUDE.md):
    // под await — только промис метода.
    const mod = await import('capacitor-native-settings');
    await mod.NativeSettings.openAndroid({ option: mod.AndroidSettings.AppNotification });
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[push] не открылись настройки уведомлений:', err);
  }
}

const closeBtn = {
  background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: 18, lineHeight: 1, padding: 4,
};

export default function PushNudge() {
  const [view, setView] = useState(null);
  const busy = useRef(false);

  const evaluate = useCallback(async () => {
    if (busy.current) return;
    const st = readNudge();
    const permission = await permissionState();
    const d = decideNudge({
      registered: true, // гостю PushNudge не рендерится (FeedScreen)
      forecastSeen: st.forecastSeen,
      choice: deviceChoice(),
      permission,
      askedAt: st.askedAt,
      cardClosed: st.cardClosed,
      now: Date.now(),
    });
    if (d === NUDGE_SILENT) {
      busy.current = true;
      await enableDeviceChannel();
      busy.current = false;
      setView(null);
      return;
    }
    if (d === NUDGE_WAIT) {
      writeNudge({ askedAt: Date.now() });
      setView(null);
      return;
    }
    setView(d === NUDGE_SCREEN || d === NUDGE_CARD || d === NUDGE_CARD_SETTINGS ? d : null);
  }, []);

  useEffect(() => {
    evaluate();
    const onVisible = () => { if (document.visibilityState === 'visible') evaluate(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [evaluate]);

  // «Включить» на экране и на карточке. Отказ (или «Не сейчас») запускает
  // отсчёт до карточки; если askedAt уже стоит, он не сдвигается.
  const enable = async () => {
    busy.current = true;
    const chosen = await enableDeviceChannel();
    if (!chosen && readNudge().askedAt == null) writeNudge({ askedAt: Date.now() });
    busy.current = false;
    setView(null);
    evaluate();
  };

  const later = () => {
    writeNudge({ askedAt: Date.now() });
    setView(null);
  };

  const closeCard = () => {
    writeNudge({ cardClosed: true });
    setView(null);
  };

  if (view === NUDGE_SCREEN) {
    return (
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Уведомления"
        style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'flex-end' }}
      >
        <div
          style={{
            width: '100%', background: 'var(--bg-page)', borderRadius: 'var(--radius-lg) var(--radius-lg) 0 0',
            padding: '18px 16px calc(18px + env(safe-area-inset-bottom))', display: 'flex', flexDirection: 'column', gap: 12,
          }}
        >
          <p style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
            Присылать прогноз каждое утро?
          </p>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            Одно уведомление в день: прогноз по твоей карте, важные транзиты и фазы Луны. Время и
            состав меняются в «Ещё» → «Уведомления».
          </p>
          <button type="button" className="mobile-btn-primary" style={{ height: 44, fontSize: 14 }} onClick={enable}>
            Включить
          </button>
          <button type="button" className="mobile-link" style={{ alignSelf: 'center' }} onClick={later}>
            Не сейчас
          </button>
        </div>
      </div>
    );
  }

  if (view === NUDGE_CARD || view === NUDGE_CARD_SETTINGS) {
    const settings = view === NUDGE_CARD_SETTINGS;
    return (
      <div style={{
        margin: '8px 16px 0', padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 10,
        border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', background: 'var(--bg-card)',
      }}
      >
        <p style={{ margin: 0, flex: 1, fontSize: 13, lineHeight: 1.45, color: 'var(--text-primary)' }}>
          Включи уведомления — прогноз будет приходить каждое утро.{' '}
          <button
            type="button"
            className="mobile-link"
            style={{ padding: 0, fontSize: 13 }}
            onClick={settings ? openNotificationSettings : enable}
          >
            {settings ? 'Открыть настройки' : 'Включить'}
          </button>
        </p>
        <button type="button" onClick={closeCard} aria-label="Скрыть" style={closeBtn}>×</button>
      </div>
    );
  }

  return null;
}
