/**
 * BirthForm — birth data input form (redesigned).
 */

import { useState, useEffect, useRef } from 'react';

const TODAY = new Date().toISOString().split('T')[0];
const MIN_DATE = '1900-01-01';

const DEFAULT_FORM = {
  name:         'Александр',
  birth_date:   '1996-05-28',
  birth_time:   '11:50',
  birth_place:  '',
  house_system: 'placidus',
};
const DEFAULT_PLACE_DISPLAY = 'Москва';
const DEFAULT_PLACE_FULL    = 'Москва, Россия';

async function nominatimSearch(query) {
  if (!query || query.length < 3) return [];
  try {
    const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=5&addressdetails=1`;
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

const S = {
  wrap: {
    background: '#fff',
    borderRadius: 20,
    boxShadow: '0 8px 40px rgba(139,92,246,0.10)',
    padding: '40px 44px 36px',
    maxWidth: 500,
    margin: '0 auto',
    border: '1px solid rgba(139,92,246,0.10)',
  },
  label: {
    display: 'block',
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.09em',
    color: '#9B97B0',
    textTransform: 'uppercase',
    marginBottom: 7,
  },
  input: {
    width: '100%',
    padding: '13px 16px',
    borderRadius: 10,
    border: '1.5px solid #EDE9FA',
    background: '#FDFBFF',
    color: '#1a1230',
    fontSize: 15,
    outline: 'none',
    fontFamily: '"Space Grotesk", system-ui, sans-serif',
    boxSizing: 'border-box',
    transition: 'border-color 0.18s',
  },
  field: { marginBottom: 20 },
  hint: { fontSize: 12, color: '#8B5CF6', marginTop: 5 },
  error: { fontSize: 12, color: '#EF4444', marginTop: 5 },
};

function Field({ label, error, hint, children }) {
  return (
    <div style={S.field}>
      {label && <label style={S.label}>{label}</label>}
      {children}
      {hint  && !error && <p style={S.hint}>{hint}</p>}
      {error && <p style={S.error} role="alert">{error}</p>}
    </div>
  );
}

function StyledInput({ error, style, ...props }) {
  const [focused, setFocused] = useState(false);
  return (
    <input
      {...props}
      style={{
        ...S.input,
        borderColor: error ? '#EF4444' : focused ? '#8B5CF6' : '#EDE9FA',
        ...style,
      }}
      onFocus={e => { setFocused(true); props.onFocus?.(e); }}
      onBlur={e => { setFocused(false); props.onBlur?.(e); }}
    />
  );
}

function PlaceInput({ value, onChange, error, defaultQuery }) {
  const [query,       setQuery]       = useState(defaultQuery || '');
  const [suggestions, setSuggestions] = useState([]);
  const [open,        setOpen]        = useState(false);
  const [coordsHint,  setCoordsHint]  = useState(defaultQuery ? `Координаты определены автоматически. Режим: Placidus System.` : '');
  const [focused,     setFocused]     = useState(false);
  const debounceRef                   = useRef(null);
  const wrapRef                       = useRef(null);

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
    setCoordsHint('');
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
    setCoordsHint('Координаты определены автоматически. Режим: Placidus System.');
  };

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <div style={{ position: 'relative' }}>
        <input
          type="text"
          value={query}
          onChange={handleChange}
          placeholder="Начните вводить город..."
          autoComplete="off"
          style={{
            ...S.input,
            borderColor: error ? '#EF4444' : focused ? '#8B5CF6' : '#EDE9FA',
            paddingRight: 40,
          }}
          onFocus={() => { setFocused(true); if (suggestions.length) setOpen(true); }}
          onBlur={() => { setTimeout(() => setOpen(false), 150); setFocused(false); }}
        />
        {/* Location icon */}
        <svg style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', opacity: 0.4 }}
          width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#8B5CF6" strokeWidth="2">
          <circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 0 0-8 8c0 5.25 8 13 8 13s8-7.75 8-13a8 8 0 0 0-8-8z"/>
        </svg>
      </div>

      {coordsHint && (
        <p style={S.hint}>{coordsHint}</p>
      )}

      {open && (
        <ul role="listbox" style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
          margin: '4px 0 0', padding: 0, listStyle: 'none',
          background: '#fff', border: '1.5px solid #EDE9FA',
          borderRadius: 12, boxShadow: '0 8px 24px rgba(139,92,246,0.12)',
          maxHeight: 220, overflowY: 'auto',
        }}>
          {suggestions.map((s, i) => (
            <li key={i} role="option" onMouseDown={() => handleSelect(s)}
              style={{
                padding: '10px 16px', fontSize: 13, color: '#1a1230',
                cursor: 'pointer',
                borderBottom: i < suggestions.length - 1 ? '1px solid #F3F0FF' : 'none',
              }}
              onMouseEnter={e => e.currentTarget.style.background = '#F8F5FF'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <div style={{ fontWeight: 600 }}>{s.short}</div>
              <div style={{ fontSize: 11, color: '#9B97B0', marginTop: 2 }}>
                {s.display.length > 60 ? s.display.slice(0, 60) + '…' : s.display}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function BirthForm({ onSubmit, loading }) {
  const [form, setForm]           = useState(DEFAULT_FORM);
  const [placeValue, setPlaceValue] = useState(DEFAULT_PLACE_FULL);
  const [timeUnknown, setTimeUnknown] = useState(false);
  const [errors, setErrors]       = useState({});

  const set = (key, val) => setForm(prev => ({ ...prev, [key]: val }));

  const fillDemo = () => {
    setForm(DEFAULT_FORM);
    setPlaceValue(DEFAULT_PLACE_FULL);
    setTimeUnknown(false);
    setErrors({});
  };

  const validate = () => {
    const errs = {};
    if (!form.name?.trim())      errs.name = 'Укажите имя';
    if (!form.birth_date)        errs.birth_date = 'Укажите дату рождения';
    if (form.birth_date < MIN_DATE) errs.birth_date = 'Дата до 1900 не поддерживается';
    if (form.birth_date > TODAY)    errs.birth_date = 'Дата не может быть в будущем';
    if (!placeValue)             errs.birth_place = 'Укажите место рождения';
    return errs;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length > 0) { setErrors(errs); return; }
    setErrors({});
    await onSubmit({
      name:         form.name.trim(),
      birth_date:   form.birth_date,
      birth_time:   timeUnknown ? null : form.birth_time || null,
      birth_place:  placeValue,
      house_system: form.house_system,
    });
  };

  return (
    <div style={S.wrap}>
      {/* Title */}
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <h2 style={{ fontSize: 22, fontWeight: 700, color: '#1a1230', margin: '0 0 6px' }}>
          Расчет натальной карты
        </h2>
        <p style={{ fontSize: 14, color: '#8B5CF6', fontWeight: 600, margin: '0 0 6px' }}>
          &amp; генерация персонального Timeline
        </p>
        <p style={{ fontSize: 13, color: '#9B97B0', margin: 0 }}>
          Астро-ядро для ИИ-анализа, планирования и экспертной работы
        </p>
      </div>

      {/* Demo mode banner */}
      <div style={{
        marginBottom: 20,
        padding: '12px 16px',
        background: '#F0FDF4',
        border: '1px solid rgba(34,197,94,0.25)',
        borderRadius: 12,
      }}>
        <p style={{ fontSize: 12, color: '#166534', margin: '0 0 10px', lineHeight: 1.5 }}>
          ⚠️ Эти данные необходимы исключительно для расчёта математических координат планет по эфемеридам (pyswisseph). Для ознакомления с интерфейсом вы можете использовать демо-данные.
        </p>
        <button
          type="button"
          onClick={fillDemo}
          style={{
            padding: '7px 18px',
            borderRadius: 20,
            border: '1.5px solid #22C55E',
            background: 'transparent',
            color: '#16A34A',
            fontSize: 13,
            fontWeight: 700,
            cursor: 'pointer',
            fontFamily: '"Space Grotesk", system-ui, sans-serif',
            transition: 'background 0.15s',
          }}
          onMouseEnter={e => e.currentTarget.style.background = '#DCFCE7'}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
        >
          ✦ Войти в демо-режим
        </button>
      </div>

      <form onSubmit={handleSubmit} noValidate>
        <Field label="Имя" error={errors.name}>
          <StyledInput
            type="text"
            value={form.name}
            onChange={e => set('name', e.target.value)}
            placeholder="Ваше имя"
            error={errors.name}
          />
        </Field>

        <Field label="Дата рождения" error={errors.birth_date}>
          <StyledInput
            type="date"
            min={MIN_DATE}
            max={TODAY}
            value={form.birth_date}
            onChange={e => set('birth_date', e.target.value)}
            error={errors.birth_date}
          />
        </Field>

        <Field label="Точное время (местное)" error={errors.birth_time}>
          <StyledInput
            type="time"
            value={form.birth_time}
            onChange={e => set('birth_time', e.target.value)}
            disabled={timeUnknown}
            error={errors.birth_time}
            style={{ opacity: timeUnknown ? 0.45 : 1, cursor: timeUnknown ? 'not-allowed' : 'text' }}
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={timeUnknown}
              onChange={e => { setTimeUnknown(e.target.checked); if (e.target.checked) set('birth_time', ''); }}
              style={{ accentColor: '#8B5CF6', width: 14, height: 14 }}
            />
            <span style={{ fontSize: 13, color: '#9B97B0' }}>
              Я не знаю точного времени (расчёт от 12:00 космограммы)
            </span>
          </label>
        </Field>

        <Field
          label="Место рождения (для расчёта домов)"
          error={errors.birth_place}
        >
          <PlaceInput
            value={placeValue}
            onChange={val => setPlaceValue(val)}
            error={errors.birth_place}
            defaultQuery={DEFAULT_PLACE_DISPLAY}
          />
        </Field>

        <button
          type="submit"
          disabled={loading}
          style={{
            width: '100%',
            padding: '15px',
            borderRadius: 50,
            border: 'none',
            background: loading
              ? 'rgba(139,92,246,0.5)'
              : 'linear-gradient(135deg, #8B5CF6, #A78BFA)',
            color: '#fff',
            fontSize: 16,
            fontWeight: 700,
            cursor: loading ? 'not-allowed' : 'pointer',
            fontFamily: '"Space Grotesk", system-ui, sans-serif',
            letterSpacing: '0.01em',
            marginTop: 8,
            transition: 'opacity 0.2s, transform 0.2s',
          }}
          onMouseEnter={e => { if (!loading) e.currentTarget.style.opacity = '0.9'; }}
          onMouseLeave={e => { e.currentTarget.style.opacity = '1'; }}
        >
          {loading ? (
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <span style={{
                width: 16, height: 16,
                border: '2px solid rgba(255,255,255,0.3)',
                borderTopColor: '#fff',
                borderRadius: '50%',
                animation: 'spin 0.8s linear infinite',
                display: 'inline-block',
              }} />
              Вычисляем карту…
            </span>
          ) : 'Рассчитать карту'}
        </button>

        {/* Footer note */}
        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: 8,
          marginTop: 18, padding: '12px 14px',
          background: '#F8F5FF', borderRadius: 10,
          border: '1px solid rgba(139,92,246,0.1)',
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#8B5CF6" strokeWidth="2"
            style={{ flexShrink: 0, marginTop: 1 }}>
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 8v4M12 16h.01"/>
          </svg>
          <p style={{ fontSize: 12, color: '#8B5CF6', margin: 0, lineHeight: 1.5 }}>
            Вычисления производятся на базе сертифицированных швейцарских эфемерид.
            Гарантированная точность планетных позиций для экспертного анализа.
          </p>
        </div>
      </form>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        input[type="date"]::-webkit-calendar-picker-indicator,
        input[type="time"]::-webkit-calendar-picker-indicator {
          filter: invert(0.4) sepia(1) saturate(3) hue-rotate(220deg);
          cursor: pointer;
          opacity: 0.6;
        }
      `}</style>
    </div>
  );
}
