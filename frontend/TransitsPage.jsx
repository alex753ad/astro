/**
 * TransitsPage — full transit page for a natal chart.
 *
 * Route: /chart/:chartId/transits
 *
 * Features:
 * - Date range picker (default: current month)
 * - Loads transits from API: GET /api/v1/chart/{id}/transits
 * - Renders TransitTimeline component
 * - Period overview AI interpretation (SSE)
 * - Tier gate: redirects to upgrade if user is free tier
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { getTransits, streamTransitInterpretation } from '../api/client';
import TransitTimeline from '../components/TransitTimeline';
import useAuth from '../hooks/useAuth';

// ── Date helpers ──────────────────────────────────────────

function toISODate(d) {
  return d.toISOString().split('T')[0];
}

function startOfMonth(d = new Date()) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function endOfMonth(d = new Date()) {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0);
}

// ═══════════════════════════════════════════════════════════
// PERIOD OVERVIEW PANEL
// ═══════════════════════════════════════════════════════════

function PeriodOverview({ chartId, fromDate, toDate }) {
  const [text,      setText]      = useState('');
  const [streaming, setStreaming] = useState(false);
  const [error,     setError]     = useState(null);
  const [open,      setOpen]      = useState(false);

  const load = useCallback(() => {
    setText('');
    setError(null);
    setStreaming(true);

    streamTransitInterpretation(
      chartId, fromDate, toDate,
      chunk => setText(prev => prev + chunk),
      ()    => setStreaming(false),
      err   => { setError(String(err)); setStreaming(false); },
    );
  }, [chartId, fromDate, toDate]);

  return (
    <div className="glass-card p-6" style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: 'var(--accent, #7C6CFF)' }}>✦</span>
          AI-обзор периода
        </h2>
        <button
          onClick={() => { setOpen(o => !o); if (!open && !text) load(); }}
          style={{
            padding: '6px 14px', borderRadius: 8,
            border: '1px solid var(--border, #1E2235)',
            background: open ? 'var(--accent-bg, rgba(124,108,255,0.1))' : 'transparent',
            color: open ? 'var(--accent, #7C6CFF)' : 'var(--text-secondary)',
            fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
          }}
        >
          {open ? 'Свернуть ▲' : 'Показать ▼'}
        </button>
      </div>

      {open && (
        <div style={{ marginTop: 16 }}>
          {streaming && !text && (
            <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Генерирую обзор…</p>
          )}
          {error && (
            <div style={{ fontSize: 13, color: '#FCA5A5', marginBottom: 10 }}>
              {error}
              <button onClick={load} style={{ marginLeft: 10, color: '#FCA5A5', background: 'none', border: '1px solid', borderRadius: 6, padding: '2px 10px', cursor: 'pointer', fontSize: 12 }}>
                Повторить
              </button>
            </div>
          )}
          {text && (
            <div style={{ fontSize: 14, lineHeight: 1.75, color: 'var(--text-primary, #E8EAF0)', whiteSpace: 'pre-wrap' }}>
              {text}
              {streaming && (
                <span style={{ display: 'inline-block', width: 7, height: 17, background: 'var(--accent)', marginLeft: 2, borderRadius: 2, animation: 'blink 0.8s step-end infinite', verticalAlign: 'text-bottom' }} />
              )}
            </div>
          )}
          <style>{`@keyframes blink{50%{opacity:0}}`}</style>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════

export default function TransitsPage() {
  const { chartId } = useParams();
  const navigate    = useNavigate();
  const { isAuthenticated, features } = useAuth();

  const [fromDate, setFromDate] = useState(toISODate(startOfMonth()));
  const [toDate,   setToDate]   = useState(toISODate(endOfMonth()));
  const [events,   setEvents]   = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');

  // Tier gate
  useEffect(() => {
    if (isAuthenticated && !features.transits) {
      navigate('/upgrade', { replace: true });
    }
  }, [isAuthenticated, features.transits, navigate]);

  const loadTransits = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getTransits(chartId, fromDate, toDate);
      setEvents(data.events ?? data);
    } catch (err) {
      setError(err.message || 'Не удалось загрузить транзиты');
    } finally {
      setLoading(false);
    }
  }, [chartId, fromDate, toDate]);

  useEffect(() => { loadTransits(); }, [loadTransits]);

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <Link to={`/chart/${chartId}`} className="text-brand-muted text-sm hover:text-brand-text transition-colors mb-2 inline-block">
          ← Назад к карте
        </Link>
        <h1 className="font-display text-2xl font-bold">Транзиты</h1>
      </div>

      {/* Date range picker */}
      <div className="glass-card p-4" style={{ marginBottom: 16, display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', gap: 12 }}>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>
            С
          </label>
          <input
            type="date"
            value={fromDate}
            onChange={e => setFromDate(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border, #1E2235)', background: 'var(--input-bg, #0F1120)', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'inherit' }}
          />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>
            По
          </label>
          <input
            type="date"
            value={toDate}
            onChange={e => setToDate(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border, #1E2235)', background: 'var(--input-bg, #0F1120)', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'inherit' }}
          />
        </div>
        <button
          onClick={loadTransits}
          disabled={loading}
          style={{
            padding: '8px 20px', borderRadius: 8, border: 'none',
            background: 'linear-gradient(135deg, #7C6CFF, #A78BFA)',
            color: '#fff', fontWeight: 600, fontSize: 13,
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.6 : 1, fontFamily: 'inherit',
          }}
        >
          {loading ? 'Загрузка…' : 'Обновить'}
        </button>

        {/* Quick range buttons */}
        {[
          { label: 'Этот месяц', fn: () => { setFromDate(toISODate(startOfMonth())); setToDate(toISODate(endOfMonth())); } },
          { label: '3 месяца',   fn: () => { const n = new Date(); setFromDate(toISODate(n)); const e = new Date(n); e.setMonth(e.getMonth() + 3); setToDate(toISODate(e)); } },
          { label: 'Год',        fn: () => { const n = new Date(); setFromDate(toISODate(n)); const e = new Date(n); e.setFullYear(e.getFullYear() + 1); setToDate(toISODate(e)); } },
        ].map(btn => (
          <button
            key={btn.label}
            onClick={btn.fn}
            style={{
              padding: '8px 14px', borderRadius: 8,
              border: '1px solid var(--border, #1E2235)',
              background: 'transparent', color: 'var(--text-secondary)',
              fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            {btn.label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div style={{ padding: '12px 16px', borderRadius: 10, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#FCA5A5', fontSize: 13, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* Period overview */}
      {events?.length > 0 && (
        <PeriodOverview chartId={chartId} fromDate={fromDate} toDate={toDate} />
      )}

      {/* Timeline */}
      <TransitTimeline
        chartId={chartId}
        events={events}
        loading={loading}
        fromDate={fromDate}
        toDate={toDate}
      />
    </div>
  );
}
