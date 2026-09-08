/**
 * ChartCreateView.jsx — форма построения натальной карты (SPEC_CHART_CREATE.md).
 *
 * Подэкран вкладки «Карта», а не отдельный маршрут: `ChartScreen` держит его
 * локальным состоянием тем же приёмом, каким `MoreScreen` держит свои
 * разделы. Маршрут дал бы только возможность размонтировать вкладку — то,
 * чего это приложение избегает (§3 спецификации).
 *
 * ⚠️ Вебовский `BirthForm.jsx` сюда не переносится, и это не «написали
 * заново по невнимательности»: там 500-пиксельная карточка, свои
 * инлайн-стили мимо мобильных токенов, наведение мышью
 * (`onMouseDown`/`onMouseEnter`) и маска даты под клавиатуру. Здесь —
 * нативные `date`/`time`, которые в webview открывают системные пикеры.
 *
 * ⚠️ Координат в запросе нет и быть не может: `POST /chart/calculate` их из
 * тела не принимает и геокодирует строку `birth_place` сам (CLAUDE.md,
 * §2.1 спецификации). Поэтому подсказки городов — украшение: строка,
 * набранная руками, работает ровно так же, а при недоступном Nominatim
 * список просто пуст (см. lib/placeSearch.js).
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import MoreSwitch from './MoreSwitch';
import { openInBrowser } from '../lib/openInBrowser';
import { PRICING_URL } from '../lib/onboardingCopy';
import { searchPlaces } from '../lib/placeSearch';
import { createChart } from '../lib/chartApi';
import { describeCreateError, validateBirthForm } from '../lib/chartCreateRules';

const EMPTY = {
  name: '',
  birthDate: '',
  birthTime: '',
  timeUnknown: false,
  birthPlace: '',
};

/** Пауза перед запросом подсказок — как на вебе (BirthForm.jsx). */
const SUGGEST_DEBOUNCE_MS = 400;

function Field({ id, label, hint, error, children }) {
  return (
    <div>
      <label className="mobile-label" htmlFor={id}>{label}</label>
      {children}
      {error
        ? <p style={{ margin: '6px 0 0', fontSize: 12.5, color: 'var(--color-danger)' }} role="alert">{error}</p>
        : hint && <p style={{ margin: '6px 0 0', fontSize: 11.5, lineHeight: 1.5, color: 'var(--text-secondary)' }}>{hint}</p>}
    </div>
  );
}

export default function ChartCreateView({ onCancel, onCreated }) {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  // Отказ в форме `describeCreateError`: у него есть вид, поле и варианты —
  // одной строкой текста этого не выразить (§7, §8 спецификации).
  const [failure, setFailure] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const debounceRef = useRef(null);
  const aliveRef = useRef(true);

  useEffect(() => () => {
    aliveRef.current = false;
    if (debounceRef.current) clearTimeout(debounceRef.current);
  }, []);

  const set = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    // Отказ относился к прежнему вводу — снимаем, как только человек начал
    // править. Иначе красная строка держится под уже исправленным полем.
    setFailure(null);
  };

  const handlePlaceChange = (value) => {
    set('birthPlace', value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      const found = await searchPlaces(value);
      if (aliveRef.current) setSuggestions(found);
    }, SUGGEST_DEBOUNCE_MS);
  };

  const submit = useCallback(async (overrides = {}) => {
    const payload = { ...form, ...overrides };
    const invalid = validateBirthForm(payload);
    if (invalid) {
      setFailure({ kind: 'form', text: invalid.text, field: invalid.field, options: [], showPricing: false });
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      const chart = await createChart(payload);
      // Отдаём id наверх: экран покажет ИМЕННО эту карту, не трогая ту,
      // что человек закрепил основной (§6 спецификации).
      onCreated(chart.id);
    } catch (err) {
      if (aliveRef.current) setFailure(describeCreateError(err));
    } finally {
      if (aliveRef.current) setBusy(false);
    }
  }, [form, onCreated]);

  const fieldError = (name) => (failure?.field === name ? failure.text : null);

  // Ветка перевода часов: не красная строка, а вопрос с выбором. Человек
  // время заполнил и, на его взгляд, правильно — сказать ему «ошибка» и
  // замолчать значит оставить его в тупике (§7 спецификации).
  const ambiguous = failure?.kind === 'ambiguous-time' ? failure : null;

  return (
    <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '12px 16px 32px' }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18 }}>
        <h1 style={{ margin: 0, flex: 1, fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 600, color: 'var(--text-primary)' }}>
          Новая карта
        </h1>
        <button type="button" className="mobile-link" onClick={onCancel} disabled={busy}>
          Отмена
        </button>
      </header>

      <form
        onSubmit={(e) => { e.preventDefault(); submit(); }}
        style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
      >
        <Field id="chart-name" label="Имя" hint="Необязательно — так карту будет проще узнать в списке" error={fieldError('name')}>
          <input
            id="chart-name"
            className={`mobile-input${fieldError('name') ? ' has-error' : ''}`}
            type="text"
            maxLength={100}
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="Например, Александр"
          />
        </Field>

        <Field id="chart-date" label="Дата рождения" error={fieldError('birthDate')}>
          <input
            id="chart-date"
            className={`mobile-input${fieldError('birthDate') ? ' has-error' : ''}`}
            type="date"
            min="1900-01-01"
            value={form.birthDate}
            onChange={(e) => set('birthDate', e.target.value)}
          />
        </Field>

        <Field
          id="chart-time"
          label="Время рождения"
          hint="Без точного времени дома и углы считаются условно, на полдень"
          error={fieldError('birthTime')}
        >
          <input
            id="chart-time"
            className={`mobile-input${fieldError('birthTime') ? ' has-error' : ''}`}
            type="time"
            value={form.birthTime}
            disabled={form.timeUnknown}
            style={form.timeUnknown ? { opacity: 0.45 } : undefined}
            onChange={(e) => set('birthTime', e.target.value)}
          />
          <button
            type="button"
            onClick={() => set('timeUnknown', !form.timeUnknown)}
            aria-pressed={form.timeUnknown}
            style={{
              marginTop: 10,
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
              padding: '10px 14px',
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 12,
              color: 'var(--text-primary)',
              fontSize: 14,
            }}
          >
            <span>Время неизвестно</span>
            <MoreSwitch on={form.timeUnknown} />
          </button>
        </Field>

        <Field
          id="chart-place"
          label="Место рождения"
          hint="Город и страна. Можно написать вручную — подсказки только помогают"
          error={fieldError('birthPlace')}
        >
          <input
            id="chart-place"
            className={`mobile-input${fieldError('birthPlace') ? ' has-error' : ''}`}
            type="text"
            autoComplete="off"
            value={form.birthPlace}
            onChange={(e) => handlePlaceChange(e.target.value)}
            placeholder="Москва, Россия"
          />
          {suggestions.length > 0 && (
            <ul
              role="listbox"
              style={{
                margin: '8px 0 0', padding: 0, listStyle: 'none',
                background: 'var(--bg-card)', border: '1px solid var(--border)',
                borderRadius: 12, overflow: 'hidden',
              }}
            >
              {suggestions.map((s, i) => (
                <li key={s.display}>
                  <button
                    type="button"
                    role="option"
                    aria-selected="false"
                    onClick={() => { set('birthPlace', s.short || s.display); setSuggestions([]); }}
                    style={{
                      width: '100%', textAlign: 'left', background: 'transparent',
                      border: 'none', padding: '11px 14px', color: 'var(--text-primary)',
                      fontSize: 13.5,
                      borderTop: i === 0 ? 'none' : '1px solid var(--border)',
                    }}
                  >
                    <span style={{ display: 'block', fontWeight: 600 }}>{s.short || s.display}</span>
                    <span style={{ display: 'block', marginTop: 2, fontSize: 11.5, color: 'var(--text-secondary)' }}>
                      {s.display.length > 64 ? `${s.display.slice(0, 64)}…` : s.display}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Field>

        {ambiguous && (
          <section
            style={{
              padding: '14px 16px',
              background: 'var(--bg-card)',
              border: '1px solid var(--color-warning)',
              borderRadius: 14,
              display: 'flex', flexDirection: 'column', gap: 10,
            }}
          >
            <p style={{ margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
              В эту ночь переводили часы
            </p>
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: 'var(--text-secondary)' }}>
              {ambiguous.text}
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {ambiguous.options.map((option) => (
                <button
                  key={option}
                  type="button"
                  disabled={busy}
                  // Выбор и подставляется в поле, и сразу уходит запросом:
                  // человек уже ответил на заданный вопрос, второе нажатие
                  // «Построить карту» ничего к его ответу не добавляет.
                  onClick={() => { set('birthTime', option); submit({ birthTime: option }); }}
                  style={{
                    padding: '9px 16px', borderRadius: 10,
                    border: '1px solid var(--accent)', background: 'transparent',
                    color: 'var(--accent)', fontSize: 14, fontWeight: 600,
                  }}
                >
                  {option}
                </button>
              ))}
            </div>
          </section>
        )}

        {failure && !ambiguous && !failure.field && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: 'var(--color-danger)' }} role="alert">
              {failure.text}
            </p>
            {/* Слоты карт кончились. Удаления карт в приложении нет (§8
                спецификации), поэтому единственный работающий ход — тарифы
                на сайте; вести туда из приложения разрешено. */}
            {failure.showPricing && (
              <button
                type="button"
                className="mobile-link"
                style={{ alignSelf: 'flex-start', padding: 0 }}
                onClick={() => openInBrowser(PRICING_URL)}
              >
                Открыть тарифы
              </button>
            )}
          </div>
        )}

        <button type="submit" className="mobile-btn-primary" disabled={busy} style={{ marginTop: 4 }}>
          {busy ? 'Строю карту…' : 'Построить карту'}
        </button>
        {busy && (
          <p style={{ margin: 0, textAlign: 'center', fontSize: 12, color: 'var(--text-secondary)' }}>
            Расчёт занимает несколько секунд
          </p>
        )}
      </form>
    </div>
  );
}
