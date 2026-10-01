/**
 * StoryShareSheet.jsx — «Поделиться днём» (флаг story_card, lib/storyCard.js).
 *
 * Два варианта на выбор (решение владельца 01.10.2026): «Моя карта» и «На
 * своё фото». Фото выбирается обычным <input type="file">: в Capacitor
 * WebView его обслуживает выбор файла Android, отдельный плагин не нужен.
 *
 * Предупреждения о данных, как в листе «Поделиться картой», здесь нет
 * намеренно: на картинке нет ни даты, ни места, ни времени рождения, ни
 * градусов, а фигура аспектов повёрнута (backend/story_card.py, шапка).
 */
import React, { useRef, useState } from 'react';
import {
  FAIL_TEXT, drawChartCard, drawPhotoCard, fetchStoryCard, loadImage, shareStoryImage,
} from '../lib/storyCard';
import { errorText } from '../lib/pdfApi';

const ACTION_STYLE = {
  width: '100%',
  minHeight: 56,
  padding: '10px 14px',
  borderRadius: 'var(--radius-md)',
  border: '1px solid var(--border)',
  background: 'var(--bg-card)',
  color: 'var(--text-primary)',
  fontFamily: 'var(--font-body)',
  fontSize: 15,
  textAlign: 'left',
  display: 'flex',
  flexDirection: 'column',
  gap: 2,
};

export default function StoryShareSheet({ chartId, date, onClose }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const fileRef = useRef(null);

  const run = async (variant, draw) => {
    setBusy(true);
    setError('');
    try {
      const card = await fetchStoryCard(chartId, date);
      if (await shareStoryImage(await draw(card), variant)) onClose();
    } catch (e) {
      setError(errorText(e, FAIL_TEXT));
    } finally {
      setBusy(false);
    }
  };

  const onPhoto = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';   // тот же файл ещё раз — снова событие change
    if (!file) return;
    let image;
    try {
      image = await loadImage(file);
    } catch (err) {
      setError(errorText(err, FAIL_TEXT));
      return;
    }
    run('photo', (card) => drawPhotoCard(card, image));
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Поделиться днём"
      onClick={busy ? undefined : onClose}
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
          Поделиться днём
        </p>

        <button type="button" disabled={busy} style={ACTION_STYLE} onClick={() => run('chart', drawChartCard)}>
          <span>Моя карта</span>
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Узор твоей карты и фраза дня</span>
        </button>
        <button type="button" disabled={busy} style={ACTION_STYLE} onClick={() => fileRef.current?.click()}>
          <span>На своё фото</span>
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Выбери фото — фраза дня встанет поверх</span>
        </button>
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={onPhoto} />

        {busy && (
          <p style={{ margin: 0, fontSize: 14, color: 'var(--text-secondary)' }}>Готовлю картинку…</p>
        )}
        {error && (
          <p role="alert" style={{ margin: 0, fontSize: 14, color: 'var(--text-secondary)' }}>{error}</p>
        )}
      </div>
    </div>
  );
}
