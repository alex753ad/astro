/**
 * InterpretView.jsx — экран разбора натальной карты
 * (SPEC_INTERPRETATION.md §9).
 *
 * Подэкран вкладки «Карта», не отдельная вкладка: `TabShell` монтирует все
 * экраны сразу и не размонтирует их, а четвёртая вкладка удлинила бы залп
 * запросов на холодном старте (разбор CLAUDE.md). Разбор при запуске не нужен
 * никогда — он идёт только по нажатию.
 *
 * ⚠️ Автозапуска нет, как и на вебе. Первый разбор free — единственный по
 * этой карте (`first_interpretation_free`), и тратить его на то, что человек
 * просто открыл экран, нельзя.
 *
 * ⚠️ Четыре исхода потока различаются на экране, а не сводятся к общему «не
 * удалось». Решение принимает `classifyOutcome` (`lib/interpretRules.js`) —
 * там же причина, там же тесты. Здесь только отрисовка того, что оно решило.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { SECTION_TITLES, stripSectionTags } from '../../lib/sectionStream';
import { startInterpretation } from '../lib/interpretApi';
import { cachedInterpretation, rememberInterpretation } from '../lib/offlineCache';
import {
  OUTCOMES,
  classifyOutcome,
  shouldCacheInterpretation,
  shouldRefetchOnResume,
  upsellForTier,
} from '../lib/interpretRules';
import useTier from '../lib/useTier';
import { openInBrowser } from '../lib/openInBrowser';
import { PRICING_URL } from '../lib/onboardingCopy';

/**
 * Разбор текста секции по строкам.
 *
 * Свой, а не вебовский `renderMarkdown` (`Interpretation.jsx:94`): тот не
 * экспортирован и тянет вебовскую вёрстку. Держим минимум — модель шлёт
 * абзацы, заголовки третьего уровня и жирный текст.
 *
 * `stripSectionTags` — подстраховка на случай, если разметка всё же
 * просочилась мимо парсера (текст, сохранённый в БД до 07.09.2026). Строка,
 * состоявшая только из тега, не рисуется вовсе — иначе на её месте останется
 * пустой абзац.
 */
function renderLines(text) {
  return text.split('\n').map((raw, i) => {
    const line = stripSectionTags(raw);
    if (line !== raw && !line.trim()) return null;
    if (!line.trim()) return <div key={i} style={{ height: 8 }} />;

    if (line.startsWith('### ') || line.startsWith('## ')) {
      return (
        <p key={i} style={{ margin: '14px 0 6px', fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>
          {line.replace(/^#+\s*/, '')}
        </p>
      );
    }

    // **жирный** — единственная инлайновая разметка, которую шлёт модель.
    const parts = line.split(/\*\*(.+?)\*\*/g);
    return (
      // Тело интерпретации — антиква (DESIGN_SYSTEM.md §3): это чтение, а не интерфейс.
      <p key={i} style={{ margin: '0 0 8px', fontFamily: 'var(--font-display)', fontSize: 15, lineHeight: 1.65, color: 'var(--text-primary)' }}>
        {parts.map((p, j) => (j % 2 ? <strong key={j}>{p}</strong> : p))}
      </p>
    );
  });
}

export default function InterpretView({ chartId, onBack }) {
  const [sections, setSections] = useState([]);   // [{ name, title, text }]
  const [started, setStarted]   = useState(false);
  const [finished, setFinished] = useState(false);
  const [failure, setFailure]   = useState(null); // результат classifyOutcome

  const closeRef   = useRef(null);
  const sectionRef = useRef(null);  // имя открытой секции
  // Разбор пришёл потоком (а не с диска) — только такой и сохраняется.
  const streamedRef = useRef(false);

  /*
   * Без сети (24.09.2026): сохранённый разбор основной карты показывается
   * сразу, как готовый. Это не автозапуск (он запрещён — см. шапку): запроса
   * нет, текст уже был получен человеком раньше.
   */
  useEffect(() => {
    let alive = true;
    cachedInterpretation(chartId).then((saved) => {
      if (!alive || !saved?.length || stateRef.current.started) return;
      setSections(saved);
      setStarted(true);
      setFinished(true);
    });
    return () => { alive = false; };
  }, [chartId]);

  useEffect(() => {
    if (!shouldCacheInterpretation({ finished, failure, streamed: streamedRef.current, sections })) return;
    streamedRef.current = false;
    rememberInterpretation(chartId, sections);
  }, [finished, failure, sections, chartId]);

  // Состояние для решения о перезапросе читается из ref, а не из замыкания:
  // обработчик visibilitychange вешается один раз и иначе видел бы значения
  // на момент подписки.
  const stateRef = useRef({ started: false, finished: false });
  stateRef.current = { started, finished };

  const stop = useCallback(() => {
    closeRef.current?.();
    closeRef.current = null;
  }, []);

  const start = useCallback(() => {
    if (!chartId) return;
    // ⚠️ Прежний поток закрывается ДО открытия нового: иначе после
    // перезапроса из фона два EventSource пишут в один экран и секции
    // перемешиваются.
    stop();
    setSections([]);
    setFailure(null);
    setFinished(false);
    setStarted(true);
    sectionRef.current = null;
    streamedRef.current = true;

    closeRef.current = startInterpretation(chartId, {
      onSectionStart: (name) => {
        sectionRef.current = name;
        setSections((prev) => [...prev, { name, title: SECTION_TITLES[name] || name, text: '' }]);
      },
      onSectionEnd: () => { sectionRef.current = null; },
      onText: (chunk) => {
        const name = sectionRef.current;
        setSections((prev) => {
          // Текст до первой секции (или после закрытия) дописывается в
          // последнюю, а при пустом списке заводит безымянный блок — иначе
          // он потерялся бы. Тот же приём, что в вебовском Interpretation.
          if (!name) {
            if (prev.length === 0) return [{ name: '_intro', title: '', text: chunk }];
            const last = prev[prev.length - 1];
            return [...prev.slice(0, -1), { ...last, text: last.text + chunk }];
          }
          return prev.map((s) => (s.name === name ? { ...s, text: s.text + chunk } : s));
        });
      },
      onDone: () => { setFinished(true); closeRef.current = null; },
      onError: (err) => {
        setFailure(classifyOutcome({ error: err }));
        setFinished(true);
        closeRef.current = null;
      },
    });
  }, [chartId, stop]);

  // Возврат из фона. Реконнекта по таймеру здесь нет намеренно: setTimeout в
  // фоне не выполняется (находка 08.09.2026), а перезапрос безопасен — см.
  // shouldRefetchOnResume, там разобрано, почему.
  useEffect(() => {
    const onVisible = () => {
      const may = shouldRefetchOnResume({
        visible: document.visibilityState === 'visible',
        open: true,           // компонент смонтирован — значит экран открыт
        started: stateRef.current.started,
        finished: stateRef.current.finished,
      });
      if (may) start();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [start]);

  // Уходим с экрана — закрываем поток. Без этого он продолжит жить и писать
  // в размонтированный компонент.
  useEffect(() => stop, [stop]);

  const hasText = sections.some((s) => s.text.trim());

  // Приписка под готовым разбором. Тексты — общий файл с вебом
  // (lib/interpretationUpsell.js), правило показа — upsellForTier
  // (lib/interpretRules.js), там же разобрано почему.
  //
  // ⚠️ Тариф берётся из ОБЩЕГО источника (useTier → /profile/subscription), а
  // не из useAuth. Прежде он приходил пропсом из useAuth, куда попадает лишь
  // с обновлением токена: пока токен жив, смена тарифа не доезжала, и на Лире
  // показывалась приписка ветки free. Пока тариф неизвестен (`known: false`)
  // приписки нет вовсе — незнание не то же самое, что бесплатный тариф.
  const { tier, known } = useTier();
  const upsell = upsellForTier({ tier, known, finished, failed: !!failure });

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <header style={{ padding: '12px 16px 8px', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
        <button
          type="button"
          onClick={onBack}
          aria-label="Назад к карте"
          style={{ background: 'transparent', border: 'none', padding: 0, color: 'var(--text-secondary)', fontSize: 20, lineHeight: 1 }}
        >
          ‹
        </button>
        <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>
          Разбор карты
        </h1>
      </header>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 16px 24px' }}>
        {!started && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 8 }}>
            <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
              Персональный разбор натальной карты — характер, таланты, жизненные темы.
            </p>
            <button type="button" className="mobile-btn-primary" style={{ height: 46 }} onClick={start}>
              Создать разбор
            </button>
          </div>
        )}

        {/* Ожидание. Процентов здесь нет намеренно: вебовский прогресс-бар
            рисует 33/66/90 по таймеру, никак не связанному с генерацией, — на
            телефоне это читается как обман. Вместо них честный срок. */}
        {started && !finished && !hasText && (
          <p style={{ margin: '8px 0 0', fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            Разбор готовится. Первые строки появятся через несколько секунд — экран можно не держать открытым.
          </p>
        )}

        {sections.map((s, i) => (
          <section key={`${s.name}-${i}`} style={{ marginTop: i === 0 ? 12 : 20 }}>
            {s.title && (
              <h2 style={{ margin: '0 0 8px', fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
                {s.title}
              </h2>
            )}
            {renderLines(s.text)}
          </section>
        ))}

        {/* Pro и premium не получают ничего — interpretationUpsell отдаёт им
            null. Предлагать более глубокий разбор тому, у кого он самый
            глубокий, незачем. */}
        {upsell?.kind === 'free' && (
          <div style={{ marginTop: 22, display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'center' }}>
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: 'var(--text-secondary)', textAlign: 'center' }}>
              {upsell.text}
            </p>
            <button
              type="button"
              className="mobile-link"
              onClick={() => openInBrowser(PRICING_URL)}
            >
              {upsell.cta}
            </button>
          </div>
        )}

        {upsell?.kind === 'lite' && (
          <div style={{ marginTop: 22, padding: '14px 16px', borderRadius: 'var(--radius-lg)', background: 'var(--bg-card)', border: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div>
              <p style={{ margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
                {upsell.title}
              </p>
              <p style={{ margin: '2px 0 0', fontSize: 12.5, color: 'var(--text-secondary)' }}>
                {upsell.subtitle}
              </p>
            </div>
            <button
              type="button"
              className="mobile-btn-primary"
              style={{ height: 44, fontSize: 13.5 }}
              onClick={() => openInBrowser(PRICING_URL)}
            >
              {upsell.cta}
            </button>
          </div>
        )}

        {/* Отказ показывается ПОД уже набранным текстом, а не вместо него:
            то, что пришло, человек уже получил — на free ценой единственного
            права по этой карте. */}
        {failure && (
          <div style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <p role="alert" style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: failure.outcome === OUTCOMES.BROKEN ? 'var(--text-secondary)' : 'var(--color-danger)' }}>
              {failure.text}
            </p>
            {failure.showPricing && (
              <button type="button" className="mobile-btn-primary" style={{ height: 44, fontSize: 14 }} onClick={() => openInBrowser(PRICING_URL)}>
                Открыть тарифы
              </button>
            )}
            {failure.canRetry && (
              <button type="button" className="mobile-link" style={{ alignSelf: 'flex-start' }} onClick={start}>
                Повторить
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
