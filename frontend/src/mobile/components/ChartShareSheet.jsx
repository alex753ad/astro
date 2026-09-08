/**
 * ChartShareSheet.jsx — лист «Поделиться картой» на экране «Карта».
 *
 * ⚠️ Это НЕ системный лист Android, и это не компромисс вёрстки: в Android
 * WebView нет `navigator.share` вовсе (разбор и доказательство — шапка
 * `lib/shareRules.js`). Настоящий системный лист требует плагина
 * `@capacitor/share`, который в проекте решено не заводить.
 *
 * ⚠️ Ссылка создаётся ТОЛЬКО по нажатию одного из двух действий, а не при
 * открытии листа. Разница содержательная: открыв лист «посмотреть, что
 * это», человек не должен получить живую публичную ссылку на свою карту.
 * Инвариант держит `mayRunShareAction` (`lib/shareRules.js`), проверяет
 * `shareRules.test.js`.
 *
 * Два действия и почему их два:
 *   · «Скопировать ссылку» — буфер обмена, как в MoreReferralView.jsx.
 *     Системного шеринга нет, поэтому копирование — единственный путь
 *     отдать ссылку в чужое приложение;
 *   · «Открыть карточку» — `openInBrowser` на `card_url`. Ручка публичная
 *     и GET (`share_router.py:457`), значит Custom Tab отдаёт PNG системе и
 *     Android сохраняет его сам. Своего кода скачивания в приложении нет и
 *     не нужно — `a.download`/blob в Capacitor WebView всё равно не
 *     работает (DownloadListener не зарегистрирован).
 */

import React, { useCallback, useState } from 'react';
import { createShareLink } from '../lib/chartApi';
import { openInBrowser } from '../lib/openInBrowser';
import {
  SHARE_DISCLOSURE,
  SHARE_STEPS,
  disclosureVisible,
  mayRunShareAction,
} from '../lib/shareRules';

const ACTION_STYLE = {
  width: '100%',
  height: 46,
  borderRadius: 12,
  border: '1px solid var(--border)',
  background: 'var(--bg-card)',
  color: 'var(--text-primary)',
  fontFamily: 'var(--font-body)',
  fontSize: 15,
};

export default function ChartShareSheet({ chartId, onClose }) {
  const [step, setStep] = useState(SHARE_STEPS.DISCLOSURE);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  const run = useCallback(async (use) => {
    if (!mayRunShareAction(step)) return;
    setStep(SHARE_STEPS.WORKING);
    setError('');
    try {
      const links = await createShareLink(chartId);
      await use(links);
      setStep(SHARE_STEPS.DISCLOSURE);
    } catch (err) {
      // Текст сервера показывается дословно: у отказа по доступу там
      // сказано, что произошло, а под общим «не удалось» это читалось бы
      // как поломка (тот же довод, что у PDF на вебе, ChartPage.jsx).
      setError(err?.message || 'Не удалось создать ссылку.');
      setStep(SHARE_STEPS.ERROR);
    }
  }, [chartId, step]);

  const copy = useCallback(() => run(async ({ shareUrl }) => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2200);
    } catch {
      // Буфер недоступен (SPEC_MORE_SCREEN.md §10) — «скопировано» не
      // показываем, раз не скопировали. Молча: обещать успех нельзя.
    }
  }), [run]);

  const openCard = useCallback(() => run(({ cardUrl }) => openInBrowser(cardUrl)), [run]);

  const busy = step === SHARE_STEPS.WORKING;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Поделиться картой"
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 60,
        background: 'rgba(0,0,0,0.45)',
        display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--bg-deeper)',
          borderTopLeftRadius: 20, borderTopRightRadius: 20,
          borderTop: '1px solid var(--border)',
          padding: '18px 16px calc(18px + env(safe-area-inset-bottom))',
          display: 'flex', flexDirection: 'column', gap: 12,
        }}
      >
        <p style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: 600, color: 'var(--text-primary)' }}>
          Поделиться картой
        </p>

        {/* Предупреждение стоит ВЫШЕ кнопок и рендерится всегда, пока лист
            открыт — см. disclosureVisible. */}
        {disclosureVisible(step) && (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
            {SHARE_DISCLOSURE.map((line) => (
              <li key={line} style={{ display: 'flex', gap: 7, fontSize: 13, lineHeight: 1.5, color: 'var(--text-secondary)' }}>
                <span aria-hidden="true">·</span>
                <span>{line}</span>
              </li>
            ))}
          </ul>
        )}

        {error && (
          <p role="alert" style={{ margin: 0, fontSize: 13, color: 'var(--color-danger)' }}>{error}</p>
        )}

        <button type="button" style={ACTION_STYLE} disabled={busy} onClick={copy}>
          {copied ? 'Ссылка скопирована' : 'Скопировать ссылку'}
        </button>
        <button type="button" style={ACTION_STYLE} disabled={busy} onClick={openCard}>
          Открыть карточку-картинку
        </button>
        <button
          type="button"
          onClick={onClose}
          style={{ ...ACTION_STYLE, background: 'transparent', border: 'none', color: 'var(--text-secondary)', height: 40 }}
        >
          Отмена
        </button>
      </div>
    </div>
  );
}
