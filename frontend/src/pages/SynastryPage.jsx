/**
 * Синастрия — совместимость сохранённой карты со второй, рассчитанной на лету.
 * Route: /synastry/:chartId. Доступ только администраторам.
 */
import { useState, useRef, useEffect } from 'react';
import { useParams, Navigate } from 'react-router-dom';
import MotionButton from '../components/MotionButton';
import NatalChart from '../components/NatalChart';
import AdvancedInterpretation from '../components/AdvancedInterpretation';
import useAuth from '../hooks/useAuth';
import { calculateSynastry, streamSynastryInterpretation } from '../api/client';

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

function isoToDisplay(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

function displayToIso(display) {
  const digits = display.replace(/\D/g, '');
  if (digits.length !== 8) return '';
  const d = digits.slice(0, 2), m = digits.slice(2, 4), y = digits.slice(4, 8);
  return `${y}-${m}-${d}`;
}

function DateMaskInput({ value, onChange, error }) {
  const [text, setText] = useState(isoToDisplay(value));
  const [focused, setFocused] = useState(false);

  const handleChange = (e) => {
    const digits = e.target.value.replace(/\D/g, '').slice(0, 8);
    let formatted = digits;
    if (digits.length > 4) formatted = `${digits.slice(0, 2)}.${digits.slice(2, 4)}.${digits.slice(4)}`;
    else if (digits.length > 2) formatted = `${digits.slice(0, 2)}.${digits.slice(2)}`;
    setText(formatted);
    onChange(displayToIso(formatted));
  };

  return (
    <input
      type="text"
      inputMode="numeric"
      placeholder="ДД.ММ.ГГГГ"
      maxLength={10}
      value={text}
      onChange={handleChange}
      style={{
        ...S.input,
        borderColor: error ? 'var(--color-danger)' : focused ? 'var(--accent)' : 'var(--border)',
      }}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
    />
  );
}

function StyledInput({ error, style, ...props }) {
  const [focused, setFocused] = useState(false);
  return (
    <input
      {...props}
      style={{
        ...S.input,
        borderColor: error ? 'var(--color-danger)' : focused ? 'var(--accent)' : 'var(--border)',
        ...style,
      }}
      onFocus={e => { setFocused(true); props.onFocus?.(e); }}
      onBlur={e => { setFocused(false); props.onBlur?.(e); }}
    />
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

// ── Таблица межкарточных аспектов ──

const ASPECT_LABELS = {
  conjunction: 'Соединение',
  sextile:     'Секстиль',
  square:      'Квадрат',
  trine:       'Трин',
  opposition:  'Оппозиция',
};

const IMPORTANCE_COLOR = {
  high:   'var(--accent)',
  medium: 'var(--text-primary)',
  low:    'var(--text-secondary)',
};

function CrossAspectTable({ aspects }) {
  if (!aspects?.length) {
    return (
      <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
        Аспектов в пределах орбов не найдено.
      </p>
    );
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ color: 'var(--text-secondary)', textAlign: 'left' }}>
            <th style={{ padding: '8px 6px', fontWeight: 600 }}>Карта 1</th>
            <th style={{ padding: '8px 6px', fontWeight: 600 }}>Аспект</th>
            <th style={{ padding: '8px 6px', fontWeight: 600 }}>Карта 2</th>
            <th style={{ padding: '8px 6px', fontWeight: 600 }}>Орб</th>
          </tr>
        </thead>
        <tbody>
          {aspects.map((a, i) => (
            <tr key={i} style={{ borderTop: '1px solid var(--border)' }}>
              <td style={{ padding: '8px 6px', color: 'var(--text-primary)' }}>{a.planet1}</td>
              <td style={{ padding: '8px 6px', color: IMPORTANCE_COLOR[a.importance] || 'var(--text-primary)' }}>
                {ASPECT_LABELS[a.aspect_type] || a.aspect_type}
              </td>
              <td style={{ padding: '8px 6px', color: 'var(--text-primary)' }}>{a.planet2}</td>
              <td style={{ padding: '8px 6px', color: 'var(--text-secondary)' }}>{a.orb}°</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Страница ──

export default function SynastryPage() {
  const { chartId } = useParams();
  const { user } = useAuth();

  const [name,        setName]        = useState('');
  const [birthDate,   setBirthDate]   = useState('');
  const [birthTime,   setBirthTime]   = useState('');
  const [timeUnknown, setTimeUnknown] = useState(false);
  const [birthPlace,  setBirthPlace]  = useState('');
  const [result,      setResult]      = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState(null);

  if (!user?.is_admin) return <Navigate to="/" replace />;

  const partner = {
    name: name || null,
    birth_date: birthDate,
    birth_time: timeUnknown ? null : (birthTime || null),
    birth_place: birthPlace,
    house_system: 'placidus',
  };

  async function handleCalculate() {
    if (!birthDate || !birthPlace) {
      setError('Заполните дату рождения и город партнёра');
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await calculateSynastry(chartId, partner));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 style={{ fontSize: 26, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
        Синастрия
      </h1>
      <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 24 }}>
        Сравнение вашей карты с картой партнёра. Карта партнёра считается на лету
        и не сохраняется.
      </p>

      <div style={{ maxWidth: 500 }}>
        <Field label="Имя партнёра">
          <StyledInput value={name} onChange={e => setName(e.target.value)} placeholder="Необязательно" />
        </Field>

        <Field label="Дата рождения">
          <DateMaskInput value={birthDate} onChange={setBirthDate} />
        </Field>

        <Field label="Время рождения" hint={timeUnknown ? 'Дома и асцендент будут неточными' : null}>
          <StyledInput
            type="time"
            value={birthTime}
            onChange={e => setBirthTime(e.target.value)}
            disabled={timeUnknown}
          />
          <label style={{
            display: 'flex', alignItems: 'center', gap: 8, marginTop: 10,
            fontSize: 13, color: 'var(--text-secondary)', cursor: 'pointer',
          }}>
            <input
              type="checkbox"
              checked={timeUnknown}
              onChange={e => setTimeUnknown(e.target.checked)}
            />
            Не знаю точное время
          </label>
        </Field>

        <Field label="Город рождения">
          <PlaceInput onChange={setBirthPlace} placeholder="Начните вводить город..." />
        </Field>

        <MotionButton onClick={handleCalculate} disabled={loading} style={{ width: '100%' }}>
          {loading ? 'Считаем…' : 'Рассчитать синастрию'}
        </MotionButton>
      </div>

      {error && (
        <p style={{ color: 'var(--color-danger)', fontSize: 14, marginTop: 14 }} role="alert">
          {error}
        </p>
      )}

      {result && (
        <div style={{ marginTop: 28 }}>
          <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
            <div style={{ flex: '1 1 320px', minWidth: 0 }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 8 }}>
                {result.chart1.name || 'Карта 1'}
              </h3>
              <NatalChart
                planets={result.chart1.planets}
                houses={result.chart1.houses}
                aspects={result.chart1.aspects}
                ascendant={result.chart1.ascendant}
                midheaven={result.chart1.midheaven}
                timeUnknown={result.chart1.time_unknown}
              />
            </div>
            <div style={{ flex: '1 1 320px', minWidth: 0 }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 8 }}>
                {result.chart2.name || 'Карта 2'}
              </h3>
              <NatalChart
                planets={result.chart2.planets}
                houses={result.chart2.houses}
                aspects={result.chart2.aspects}
                ascendant={result.chart2.ascendant}
                midheaven={result.chart2.midheaven}
                timeUnknown={result.chart2.time_unknown}
              />
            </div>
          </div>

          <h2 style={{
            fontSize: 16, fontWeight: 700, color: 'var(--text-primary)',
            marginTop: 28, marginBottom: 12,
          }}>
            Межкарточные аспекты
          </h2>
          <CrossAspectTable aspects={result.cross_aspects} />

          <AdvancedInterpretation
            buttonLabel="Получить разбор совместимости"
            start={(onChunk, onDone, onError) =>
              streamSynastryInterpretation(chartId, partner, onChunk, onDone, onError)
            }
          />
        </div>
      )}
    </div>
  );
}
