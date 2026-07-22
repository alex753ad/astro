/**
 * Релокация — натальная карта, пересчитанная на координаты другого города.
 * Route: /relocation/:chartId. Доступ только администраторам.
 */
import { useState, useRef, useEffect } from 'react';
import { useParams, Navigate } from 'react-router-dom';
import MotionButton from '../components/MotionButton';
import NatalChart from '../components/NatalChart';
import AdvancedInterpretation from '../components/AdvancedInterpretation';
import useAuth from '../hooks/useAuth';
import { calculateRelocation, streamRelocationInterpretation, getChart } from '../api/client';

// ── Подкомпоненты формы (скопированы из BirthForm.jsx) ──

const S = {
  label: {
    display: 'block', fontSize: 11, fontWeight: 700, letterSpacing: '0.09em',
    color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: 7,
  },
  input: {
    width: '100%', padding: '13px 16px', borderRadius: 10,
    border: '1.5px solid var(--border)', background: 'var(--bg-deeper)',
    color: 'var(--text-primary)', fontSize: 15, outline: 'none',
    fontFamily: '"Space Grotesk", system-ui, sans-serif',
    boxSizing: 'border-box', transition: 'border-color 0.18s',
  },
  field: { marginBottom: 18 },
  hint:  { fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 },
  error: { fontSize: 12, color: 'var(--color-danger)', marginTop: 6 },
};

async function nominatimSearch(query) {
  if (!query || query.length < 3) return [];
  try {
    const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=5&addressdetails=1&accept-language=ru`;
    const resp = await fetch(url, { headers: { 'Accept-Language': 'ru,en' } });
    const data = await resp.json();
    return data.map(d => ({
      display: d.display_name,
      short: [d.address?.city || d.address?.town || d.address?.village, d.address?.country]
        .filter(Boolean).join(', '),
    }));
  } catch {
    return [];
  }
}

function Field({ label, error, hint, children }) {
  return (
    <div style={S.field}>
      {label && <label style={S.label}>{label}</label>}
      {children}
      {hint && !error && <p style={S.hint}>{hint}</p>}
      {error && <p style={S.error} role="alert">{error}</p>}
    </div>
  );
}

function PlaceInput({ onChange, placeholder }) {
  const [query,       setQuery]       = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [open,        setOpen]        = useState(false);
  const [focused,     setFocused]     = useState(false);
  const debounceRef = useRef(null);
  const wrapRef     = useRef(null);

  useEffect(() => {
    function handler(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleChange = (e) => {
    const q = e.target.value;
    setQuery(q);
    onChange('');
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      const results = await nominatimSearch(q);
      setSuggestions(results);
      setOpen(results.length > 0);
    }, 400);
  };

  const handleSelect = (s) => {
    setQuery(s.short || s.display);
    onChange(s.display);
    setSuggestions([]);
    setOpen(false);
  };

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <input
        type="text"
        value={query}
        onChange={handleChange}
        placeholder={placeholder}
        autoComplete="off"
        style={{ ...S.input, borderColor: focused ? 'var(--accent)' : 'var(--border)' }}
        onFocus={() => { setFocused(true); if (suggestions.length) setOpen(true); }}
        onBlur={() => { setTimeout(() => setOpen(false), 150); setFocused(false); }}
      />
      {open && (
        <ul role="listbox" style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
          margin: '4px 0 0', padding: 0, listStyle: 'none',
          background: 'var(--bg-card)', border: '1.5px solid var(--border)',
          borderRadius: 12, boxShadow: '0 8px 24px rgba(139,92,246,0.12)',
          maxHeight: 220, overflowY: 'auto',
        }}>
          {suggestions.map((s, i) => (
            <li key={i} role="option" onMouseDown={() => handleSelect(s)}
              style={{
                padding: '10px 16px', fontSize: 13, color: 'var(--text-primary)',
                cursor: 'pointer',
                borderBottom: i < suggestions.length - 1 ? '1px solid var(--border)' : 'none',
              }}>
              <div style={{ fontWeight: 600 }}>{s.short}</div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                {s.display.length > 60 ? s.display.slice(0, 60) + '…' : s.display}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Сравнение домов ──

function HouseColumn({ title, houses }) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <h3 style={{
        fontSize: 11, fontWeight: 700, letterSpacing: '0.09em',
        textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 10,
      }}>
        {title}
      </h3>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {(houses || []).map(h => (
          <li key={h.number} style={{
            display: 'flex', justifyContent: 'space-between', gap: 8,
            padding: '6px 0', borderBottom: '1px solid var(--border)',
            fontSize: 13, color: 'var(--text-primary)',
          }}>
            <span style={{ color: 'var(--text-secondary)' }}>{h.number}</span>
            <span>{h.sign} {Math.round(h.degree)}°</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Страница ──

export default function RelocationPage() {
  const { chartId } = useParams();
  const { user } = useAuth();

  const [location,  setLocation]  = useState('');
  const [relocated, setRelocated] = useState(null);
  const [natal,     setNatal]     = useState(null);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState(null);

  // Натальные дома нужны для колонки сравнения.
  useEffect(() => {
    if (!user?.is_admin || !chartId) return;
    getChart(chartId).then(setNatal).catch(() => setNatal(null));
  }, [chartId, user]);

  if (!user?.is_admin) return <Navigate to="/" replace />;

  async function handleCalculate() {
    if (!location) { setError('Выберите город из подсказок'); return; }
    setLoading(true);
    setError(null);
    setRelocated(null);
    try {
      setRelocated(await calculateRelocation(chartId, location));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <h1 style={{ fontSize: 26, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
        Релокация
      </h1>
      <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 24 }}>
        Дата и время рождения остаются прежними — меняются только координаты.
        Планеты сохраняют знаки и аспекты, но переходят в другие дома.
      </p>

      <Field label="Новый город">
        <PlaceInput onChange={setLocation} placeholder="Начните вводить город..." />
      </Field>

      <MotionButton onClick={handleCalculate} disabled={loading} style={{ width: '100%' }}>
        {loading ? 'Считаем…' : 'Рассчитать релокацию'}
      </MotionButton>

      {error && (
        <p style={{ color: 'var(--color-danger)', fontSize: 14, marginTop: 14 }} role="alert">
          {error}
        </p>
      )}

      {relocated && (
        <div style={{ marginTop: 28 }}>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 14 }}>
            Карта для: <strong>{relocated.relocated_location}</strong>
          </p>

          <NatalChart
            planets={relocated.planets}
            houses={relocated.houses}
            aspects={relocated.aspects}
            ascendant={relocated.ascendant}
            midheaven={relocated.midheaven}
            timeUnknown={relocated.time_unknown}
          />

          <div style={{ display: 'flex', gap: 24, marginTop: 24 }}>
            <HouseColumn title="Натальные дома" houses={natal?.houses} />
            <HouseColumn title="Дома в релокации" houses={relocated.houses} />
          </div>

          <AdvancedInterpretation
            buttonLabel="Получить разбор переезда"
            start={(onChunk, onDone, onError) =>
              streamRelocationInterpretation(chartId, location, onChunk, onDone, onError)
            }
          />
        </div>
      )}
    </div>
  );
}
