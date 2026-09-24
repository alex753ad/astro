/**
 * OfflineNote.jsx — тихая пометка над сохранённым: «Без сети · данные от 08:14».
 *
 * Не баннер и не ошибка (решение владельца 24.09.2026): человек видит свои
 * данные, а пометка лишь говорит, насколько они свежие. Время — по часам
 * телефона; не сегодня — с датой.
 */
import React from 'react';

export function savedAtLabel(savedAt, now = new Date()) {
  const d = new Date(savedAt);
  if (Number.isNaN(d.getTime())) return '';
  const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  const sameDay = d.toDateString() === now.toDateString();
  return sameDay ? time : `${d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })}, ${time}`;
}

export function offlineNoteText(savedAt, kind, now) {
  const head = kind === 'server' ? 'Сервер не отвечает' : 'Без сети';
  const at = savedAtLabel(savedAt, now);
  return at ? `${head} · данные от ${at}` : head;
}

export default function OfflineNote({ savedAt, kind }) {
  if (!savedAt) return null;
  return (
    <p role="status" style={{ margin: '6px 0', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center' }}>
      {offlineNoteText(savedAt, kind)}
    </p>
  );
}
