/**
 * PushNudge.jsx — зовём включить уведомления (решение владельца 30.09.2026).
 * Кому и что показывать, решает lib/pushNudge.js (`decideNudge`, с тестом);
 * здесь — только показ и последствия ответа.
 *
 * ⚠️ Когда проверять (исправлено после приёмки APK №119, 30.09.2026).
 * Вкладки в TabShell не пересоздаются, а прячутся, — «открытие ленты»
 * случается один раз, когда прогноз ещё готовится, и отметки нет. Поэтому
 * поводов пять: открытие ленты, загрузка прогноза (событие
 * FORECAST_SEEN_EVENT), возврат на вкладку «Лента» (`active`), возврат в
 * приложение (visibilitychange + focus + pageshow, как в useAuth.jsx —
 * одного visibilitychange в WebView может не прийти) и нажатие кнопки.
 * На поводе «прогноз загрузился» экран НЕ показывается — он ждёт следующего
 * повода, чтобы не встать поверх прогноза; молчаливое включение и отсчёт —
 * сразу.
 *
 * ⚠️ Молчаливое включение не вышло — ничего не записываем: тумблер остаётся
 * «не трогали», и следующая проверка попробует снова.
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
  FORECAST_SEEN_EVENT, decideNudge, readNudge, writeNudge,
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

export default function PushNudge({ active }) {
  const [view, setView] = useState(null);
  const busy = useRef(false);

  const evaluate = useCallback(async (trigger) => {
    if (busy.current) return;
    busy.current = true;
    try {
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
      const last = { at: Date.now(), trigger, result: d, permission, enable: st.last?.enable || null };
      if (d === NUDGE_SILENT) {
        last.enable = (await enableDeviceChannel()) || 'fail';
        writeNudge({ last });
        setView(null);
        return;
      }
      writeNudge(d === NUDGE_WAIT ? { askedAt: Date.now(), last } : { last });
      if (d === NUDGE_SCREEN && trigger === 'forecast') return; // не поверх прогноза
      setView(d === NUDGE_SCREEN || d === NUDGE_CARD || d === NUDGE_CARD_SETTINGS ? d : null);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[push] проверка «включи уведомления»:', err);
    } finally {
      // ⚠️ Только в finally: ошибка внутри раньше оставляла busy навсегда
      // и выключала все следующие проверки.
      busy.current = false;
    }
  }, []);

  useEffect(() => {
    evaluate('mount');
    const onResume = () => { if (document.visibilityState === 'visible') evaluate('resume'); };
    const onForecast = () => evaluate('forecast');
    document.addEventListener('visibilitychange', onResume);
    window.addEventListener('focus', onResume);
    window.addEventListener('pageshow', onResume);
    window.addEventListener(FORECAST_SEEN_EVENT, onForecast);
    return () => {
      document.removeEventListener('visibilitychange', onResume);
      window.removeEventListener('focus', onResume);
      window.removeEventListener('pageshow', onResume);
      window.removeEventListener(FORECAST_SEEN_EVENT, onForecast);
    };
  }, [evaluate]);

  // Возврат на вкладку «Лента»: смена active с false на true.
  const wasActive = useRef(active);
  useEffect(() => {
    if (active && wasActive.current === false) evaluate('tab');
    wasActive.current = active;
  }, [active, evaluate]);

  // «Включить» на экране и на карточке. Отказ (или «Не сейчас») запускает
  // отсчёт до карточки; если askedAt уже стоит, он не сдвигается.
  const enable = async () => {
    busy.current = true;
    let chosen = null;
    try {
      chosen = await enableDeviceChannel();
    } finally {
      const st = readNudge();
      writeNudge({
        last: { ...(st.last || {}), at: Date.now(), trigger: 'button', enable: chosen || 'fail' },
        ...(!chosen && st.askedAt == null ? { askedAt: Date.now() } : {}),
      });
      busy.current = false;
    }
    setView(null);
    evaluate('button');
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
