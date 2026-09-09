import { describe, expect, it } from 'vitest';

import { transitTeaserText } from './transitTeaser';

/**
 * transitTeaser.test.js — тизер говорит о конкретном транзите.
 *
 * ⚠️ Что чинится. Сервер отдавал одну и ту же фразу на все события подряд
 * («Это активный период по одной из ключевых тем вашей карты…»,
 * `feed/templates.json`). Человек, открывший десять карточек, десять раз
 * читал одно и то же — продать такое нельзя.
 *
 * Главный тест здесь — не «строка непустая», а что РАЗНЫЕ транзиты дают
 * РАЗНЫЕ строки, и что на реальном наборе событий одинаковых не остаётся.
 */

const ev = (transit_planet, natal_planet, aspect_type, extra = {}) => ({
  kind: 'transit',
  meta: { transit_planet, natal_planet, aspect_type, ...extra },
});

describe('строка собирается из данных события', () => {
  it('образец тона владельца воспроизводится дословно', () => {
    expect(transitTeaserText(ev('Sun', 'Neptune', 'square')))
      .toBe('Солнце к вашему Нептуну: тема ясности и иллюзий. Напряжённый аспект, окно около недели.');
  });

  it('род согласован: «к вашей Луне», а не «к вашему»', () => {
    expect(transitTeaserText(ev('Saturn', 'Moon', 'trine'))).toContain('к вашей Луне');
    expect(transitTeaserText(ev('Saturn', 'Venus', 'trine'))).toContain('к вашей Венере');
    expect(transitTeaserText(ev('Saturn', 'Mars', 'trine'))).toContain('к вашему Марсу');
  });

  it('одинаковая тема не удваивается', () => {
    // «тема ясности и ясности» — брак, а Солнце к натальному Солнцу событие
    // ежегодное.
    const s = transitTeaserText(ev('Sun', 'Sun', 'conjunction'));
    expect(s).toContain('тема ясности.');
    expect(s).not.toContain('ясности и ясности');
  });

  it('характер аспекта — тип связи, а не оценка', () => {
    expect(transitTeaserText(ev('Mars', 'Sun', 'square'))).toContain('Напряжённый аспект');
    expect(transitTeaserText(ev('Mars', 'Sun', 'trine'))).toContain('Мягкий аспект');
    expect(transitTeaserText(ev('Mars', 'Sun', 'conjunction'))).toContain('Соединение');
  });

  it('окно зависит от транзитной планеты, а не от натальной', () => {
    expect(transitTeaserText(ev('Moon', 'Pluto', 'square'))).toContain('несколько часов');
    expect(transitTeaserText(ev('Pluto', 'Moon', 'square'))).toContain('до года');
  });
});

describe('разные транзиты — разные строки', () => {
  it('смена любой из трёх частей меняет строку', () => {
    const base = transitTeaserText(ev('Sun', 'Neptune', 'square'));
    expect(transitTeaserText(ev('Mars', 'Neptune', 'square'))).not.toBe(base);
    expect(transitTeaserText(ev('Sun', 'Saturn', 'square'))).not.toBe(base);
    expect(transitTeaserText(ev('Sun', 'Neptune', 'trine'))).not.toBe(base);
  });

  it('на наборе из десяти разных событий одинаковых строк не остаётся', () => {
    const events = [
      ev('Sun', 'Neptune', 'square'), ev('Moon', 'Venus', 'trine'),
      ev('Saturn', 'Sun', 'opposition'), ev('Pluto', 'Moon', 'conjunction'),
      ev('Mars', 'Mercury', 'sextile'), ev('Jupiter', 'Venus', 'trine'),
      ev('Uranus', 'Mars', 'square'), ev('Neptune', 'Mercury', 'opposition'),
      ev('Venus', 'Jupiter', 'conjunction'), ev('Mercury', 'Saturn', 'square'),
    ];
    const lines = events.map(transitTeaserText);
    expect(lines.every(Boolean)).toBe(true);
    expect(new Set(lines).size).toBe(lines.length);
  });
});

describe('трактовки нет — это граница, а не недоделка', () => {
  it('ни совета, ни оценки, ни предсказания', () => {
    const events = [
      ev('Sun', 'Neptune', 'square'), ev('Saturn', 'Moon', 'opposition'),
      ev('Pluto', 'Venus', 'conjunction'), ev('Mars', 'Mercury', 'square'),
    ];
    // Что с этим делать и как проявится — остаётся платному разбору.
    const forbidden = /стоит|лучше|избегай|осторожн|удач|опасн|повезёт|получится|нужно/i;
    for (const e of events) {
      expect(transitTeaserText(e)).not.toMatch(forbidden);
    }
  });
});

describe('чего нет в meta — не выдумываем', () => {
  it('незнакомая планета — отказ целиком, а не строка с латиницей', () => {
    expect(transitTeaserText(ev('Chiron', 'Sun', 'square'))).toBeNull();
    expect(transitTeaserText(ev('Sun', 'Chiron', 'square'))).toBeNull();
  });

  it('незнакомый аспект — отказ', () => {
    expect(transitTeaserText(ev('Sun', 'Moon', 'quincunx'))).toBeNull();
  });

  it('пустая meta — отказ', () => {
    expect(transitTeaserText({ kind: 'transit' })).toBeNull();
    expect(transitTeaserText({ kind: 'transit', meta: {} })).toBeNull();
  });

  it('не транзит — своей строки нет', () => {
    // У лунных фаз и периодов планера остаётся серверный текст.
    expect(transitTeaserText({ kind: 'moon_phase', meta: {} })).toBeNull();
    expect(transitTeaserText({ kind: 'planner_period', meta: {} })).toBeNull();
  });

  it('отказ означает запасной путь, а не пустоту на экране', () => {
    // Панель показывает серверный тизер, когда здесь null — проверяется тем,
    // что null отличим от пустой строки.
    expect(transitTeaserText(ev('Chiron', 'Sun', 'square'))).toBeNull();
    expect(transitTeaserText(ev('Chiron', 'Sun', 'square'))).not.toBe('');
  });
});
