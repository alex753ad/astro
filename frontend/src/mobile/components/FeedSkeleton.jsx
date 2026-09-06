/**
 * FeedSkeleton.jsx — состояние загрузки ленты (§11 спецификации).
 *
 * По спецификации скелет — «полоса сверху + 3 карточки». Полосы «сейчас»
 * (§4) в этом заходе ещё нет, поэтому здесь только три карточки; полоса
 * добавится сюда же вместе с самой полосой, вторым заходом.
 *
 * Скелет повторяет РАЗМЕРЫ настоящей карточки, а не рисует абстрактные
 * прямоугольники: иначе в момент подстановки данных лента прыгает, и это
 * читается как подтормаживание, хотя ничего не тормозит.
 */

import React from 'react';

function SkeletonLine({ width, height = 12 }) {
  return (
    <div
      className="mobile-skeleton"
      style={{ width, height, borderRadius: 6, background: 'var(--border)' }}
    />
  );
}

function SkeletonCard() {
  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 20,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <SkeletonLine width="18%" height={10} />
      <SkeletonLine width="72%" height={18} />
      <SkeletonLine width="46%" />
    </div>
  );
}

export default function FeedSkeleton() {
  return (
    <div
      aria-busy="true"
      aria-label="Лента загружается"
      style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
    >
      <SkeletonLine width="40%" height={13} />
      <SkeletonCard />
      <SkeletonCard />
      <SkeletonCard />
    </div>
  );
}
