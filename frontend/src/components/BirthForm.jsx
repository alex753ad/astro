/**
 * BirthForm — birth data input form.
 */

import { useState, useEffect, useRef } from 'react';

const TODAY = new Date().toISOString().split('T')[0];
const MIN_DATE = '1900-01-01';

// ── Default values ──
const DEFAULT_FORM = {
  birth_date:   '1990-06-01',
  birth_time:   '00:20',
  birth_place:  '',
  house_system: 'placidus',
};
const DEFAULT_PLACE_DISPLAY = 'Новочеркасск, Россия';
const DEFAULT_PLACE_FULL    = 'Новочеркасск, городской округ Новочеркасск, Ростовская область, Россия';

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

const inputStyle = {
  width: '100%',
  padding: '12px 14px',
  borderRadius: 10,
  border: '1.5px solid var(--border, #1E2235)',
  background: 'var(--input-bg, #0F1120)',
  color: 'var(--text-primary, #E8EAF0)',
  fontSize: 15,
  outline: 'none',
  transition: 'border-color 0.2s ease',
  fontFamily: 'inherit',
  boxSizing: 'border-box',
};

const labelStyle = {
  display: 'block',
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--text-secondary, #8B8FA3)',
  marginBottom: 6,
  letterSpacing: '0.03em',
};

function PlaceInput({ value, onChange, error, defaultQuery }) {
  const [query,       setQuery]       = useState(defaultQuery || '');
  const [suggestions, setSuggestions] = useState([]);
  const [open,        setOpen]        = useState(false);
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
        placeholder="Например: Москва, Россия"
        aria-label="Место рождения"
        aria-autocomplete="list"
        aria-expanded={open}
        autoComplete="off"
        style={{
          ...inputStyle,
          borderColor: error ? '#EF4444' : undefined,
        }}
        onFocus={e => {
          e.target.style.borderColor = 'var(--accent, #7C6CFF)';
          if (suggestions.length) setOpen(true);
        }}
        onBlur={e => {
          setTimeout(() => setOpen(false), 150);
          e.target.style.borderColor = error ? '#EF4444' : 'var(--border, #1E2235)';
        }}
      />
      {open && (
        <ul
          role="listbox"
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            zIndex: 50,
            margin: '4px 0 0',
            padding: 0,
            listStyle: 'none',
            background: 'var(--card-bg, #141620)',
            border: '1px solid var(--border, #1E2235)',
            borderRadius: 10,
            boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
            maxHeight: 220,
            overflowY: 'auto',
          }}
        >
          {suggestions.map((s, i) => (
            <li
              key={i}
              role="option"
              onMouseDown={() => handleSelect(s)}
              style={{
                padding: '10px 14px',
                fontSize: 13,
                color: 'var(--text-primary, #E8EAF0)',
                cursor: 'pointer',
                borderBottom: i < suggestions.length - 1 ? '1px solid var(--border, #1E2235)' : 'none',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--accent-bg, rgba(124,108,255,0.1))'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <div style={{ fontWeight: 500 }}>{s.short}</div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary, #8B8FA3)', marginTop: 2 }}>
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
  const [form, setForm] = useState(DEFAULT_FORM);
  const [placeValue, setPlaceValue] = useState(DEFAULT_PLACE_FULL);
  const [timeUnknown, setTimeUnknown] = useState(false);
  const [errors, setErrors] = useState({});

  const set = (key, val) => setForm(prev => ({ ...prev, [key]: val }));

  const validate = () => {
    const errs = {};
    if (!form.birth_date) errs.birth_date = 'Укажите дату рождения';
    if (form.birth_date < MIN_DATE) errs.birth_date = 'Дата до 1900 года не поддерживается';
    if (form.birth_date > TODAY)    errs.birth_date = 'Дата рождения не может быть в будущем';
    if (!placeValue) errs.birth_place = 'Укажите место рождения';
    return errs;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }
    setErrors({});
    await onSubmit({
      birth_date:   form.birth_date,
      birth_time:   timeUnknown ? null : form.birth_time || null,
      birth_place:  placeValue,
      house_system: form.house_system,
    });
  };

  const fieldGroup = (label, field, children, hint) => (
    <div style={{ marginBottom: 18 }}>
      <label style={labelStyle} htmlFor={field}>{label}</label>
      {children}
      {hint && <p style={{ margin: '5px 0 0', fontSize: 12, color: 'var(--text-secondary, #8B8FA3)' }}>{hint}</p>}
      {errors[field] && (
        <p style={{ margin: '5px 0 0', fontSize: 12, color: '#EF4444' }} role="alert">{errors[field]}</p>
      )}
    </div>
  );

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      style={{ maxWidth: 480, margin: '0 auto' }}
      aria-label="Форма ввода данных рождения"
    >
      {fieldGroup('Дата рождения', 'birth_date',
        <input
          id="birth_date"
          type="date"
          min={MIN_DATE}
          max={TODAY}
          value={form.birth_date}
          onChange={e => set('birth_date', e.target.value)}
          required
          style={{
            ...inputStyle,
            borderColor: errors.birth_date ? '#EF4444' : undefined,
          }}
          onFocus={e => e.target.style.borderColor = 'var(--accent, #7C6CFF)'}
          onBlur={e => e.target.style.borderColor = errors.birth_date ? '#EF4444' : 'var(--border, #1E2235)'}
        />
      )}

      {fieldGroup('Время рождения', 'birth_time',
        <div>
          <input
            id="birth_time"
            type="time"
            value={form.birth_time}
            onChange={e => set('birth_time', e.target.value)}
            disabled={timeUnknown}
            style={{
              ...inputStyle,
              opacity: timeUnknown ? 0.4 : 1,
              cursor: timeUnknown ? 'not-allowed' : 'text',
            }}
            onFocus={e => !timeUnknown && (e.target.style.borderColor = 'var(--accent, #7C6CFF)')}
            onBlur={e => e.target.style.borderColor = 'var(--border, #1E2235)'}
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={timeUnknown}
              onChange={e => {
                setTimeUnknown(e.target.checked);
                if (e.target.checked) set('birth_time', '');
              }}
              style={{ accentColor: 'var(--accent, #7C6CFF)', width: 15, height: 15 }}
            />
            <span style={{ fontSize: 13, color: 'var(--text-secondary, #8B8FA3)' }}>
              Время неизвестно (расчёт на 12:00)
            </span>
          </label>
        </div>,
        timeUnknown ? 'Дома и Асцендент будут помечены как неточные.' : null
      )}

      {fieldGroup('Место рождения', 'birth_place',
        <PlaceInput
          value={placeValue}
          onChange={val => setPlaceValue(val)}
          error={errors.birth_place}
          defaultQuery={DEFAULT_PLACE_DISPLAY}
        />,
        'Начните вводить город — появятся подсказки.'
      )}

      {fieldGroup('Система домов', 'house_system',
        <select
          id="house_system"
          value={form.house_system}
          onChange={e => set('house_system', e.target.value)}
          style={{ ...inputStyle, cursor: 'pointer' }}
        >
          <option value="placidus">Плацидус (по умолчанию)</option>
          <option value="koch">Кох</option>
          <option value="whole_sign">Целые знаки</option>
          <option value="equal">Равные дома</option>
        </select>
      )}

      <button
        type="submit"
        disabled={loading}
        style={{
          width: '100%',
          padding: '14px',
          borderRadius: 12,
          border: 'none',
          background: loading
            ? 'rgba(124,108,255,0.4)'
            : 'linear-gradient(135deg, #7C6CFF, #A78BFA)',
          color: '#fff',
          fontSize: 16,
          fontWeight: 700,
          cursor: loading ? 'not-allowed' : 'pointer',
          transition: 'all 0.2s ease',
          fontFamily: 'inherit',
          letterSpacing: '0.02em',
        }}
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
        ) : 'Рассчитать натальную карту ✦'}
      </button>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        input[type="date"]::-webkit-calendar-picker-indicator,
        input[type="time"]::-webkit-calendar-picker-indicator {
          filter: invert(0.7);
          cursor: pointer;
        }
      `}</style>
    </form>
  );
}
