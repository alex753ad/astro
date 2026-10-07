// Граница ошибок вокруг вкладки ChartPage: упавшая вкладка не роняет страницу
// в белый экран (так было в #123 — ReferenceError во вкладке транзитов).
// Sentry.ErrorBoundary — чтобы ошибка ушла в Sentry тем же путём и с тем же
// scrubEvent, что и остальные ошибки фронта; без VITE_SENTRY_DSN — no-op.
// Сброс при смене вкладки — через key у TabBoundary в ChartPage.
import * as Sentry from '@sentry/react';
import MotionButton from './MotionButton';

export default function TabBoundary({ children }) {
  return (
    <Sentry.ErrorBoundary
      fallback={({ resetError }) => (
        <div role="alert" style={{ padding: 40, textAlign: 'center', color: 'var(--text-secondary)', fontSize: 14, borderRadius: 'var(--radius-lg)', border: '1.5px dashed var(--accent-hairline)', background: 'var(--bg)' }}>
          Не удалось показать этот раздел.<br />
          <span style={{ fontSize: 12, opacity: 0.7 }}>Попробуй ещё раз — остальная страница работает.</span>
          <div style={{ marginTop: 16 }}>
            <MotionButton level="primary" onClick={resetError}>Повторить</MotionButton>
          </div>
        </div>
      )}
    >
      {children}
    </Sentry.ErrorBoundary>
  );
}
