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
      .toBe('Солнце к твоему Нептуну: тема ясности и иллюзий. Напряжённый аспект, окно около недели.');
  });

  it('род согласован: «к твоей Луне», а не «к твоему»', () => {
    expect(transitTeaserText(ev('Saturn', 'Moon', 'trine'))).toContain('к твоей Луне');
    expect(transitTeaserText(ev('Saturn', 'Venus', 'trine'))).toContain('к твоей Венере');
    expect(transitTeaserText(ev('Saturn', 'Mars', 'trine'))).toContain('к твоему Марсу');
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

describe('планета к своей же точке', () => {
  const own = (planet, aspect) => ev(planet, planet, aspect);

  it('фраза не обрывается на половине конструкции', () => {
    // Было: «Луна к твоей Луне: тема чувств.» — пара тем схлопнулась, и от
    // конструкции осталась половина.
    expect(transitTeaserText(own('Moon', 'conjunction')))
      .toBe('Луна к твоей Луне: начало собственного цикла, тема чувств. Соединение, окно несколько часов.');
  });

  it('возвращением называется ТОЛЬКО соединение', () => {
    // Главное, что здесь легко сделать неправильно. На боевых лентах у
    // совпадающих пар встречаются все пять аспектов, и соединений среди них
    // меньшинство (6-7 из ~65 на карту). Луна в квадрате к своей натальной
    // Луне никуда не возвращается — она проходит четверть круга.
    expect(transitTeaserText(own('Moon', 'conjunction'))).toContain('начало собственного цикла');
    expect(transitTeaserText(own('Moon', 'square'))).toContain('четверть собственного цикла');
    expect(transitTeaserText(own('Moon', 'opposition'))).toContain('середина собственного цикла');
  });

  it('все пять аспектов дают осмысленную фразу', () => {
    // Ни один не должен провалиться в запасной путь: они все встречаются.
    for (const a of ['conjunction', 'opposition', 'square', 'trine', 'sextile']) {
      const s = transitTeaserText(own('Sun', a));
      expect(s, a).toBeTruthy();
      expect(s, a).toContain('собственного цикла');
    }
  });

  it('фаза цикла различает строки, а характер аспекта остаётся', () => {
    const square = transitTeaserText(own('Venus', 'square'));
    const opposition = transitTeaserText(own('Venus', 'opposition'));
    expect(square).not.toBe(opposition);
    // Оба напряжённые — характер аспекта из фразы не пропал.
    expect(square).toContain('Напряжённый аспект');
    expect(opposition).toContain('Напряжённый аспект');
  });

  it('тема планеты называется один раз, а не дважды', () => {
    const s = transitTeaserText(own('Sun', 'trine'));
    expect(s).toContain('тема ясности.');
    expect(s).not.toContain('ясности и ясности');
  });

  it('у самого частого случая формулировка живая, а не канцелярская', () => {
    // Тригон и секстиль — 169 строк из 333 на боевой ленте, то есть больше
    // половины совпадающих пар. «Промежуточная точка собственного цикла»
    // досталась бы именно им.
    expect(transitTeaserText(own('Moon', 'trine')))
      .toBe('Луна к твоей Луне: между ключевыми точками собственного цикла, тема чувств. Мягкий аспект, окно несколько часов.');
    expect(transitTeaserText(own('Moon', 'sextile'))).toContain('между ключевыми точками');
  });

  it('фаза не пропадает ни у одного аспекта', () => {
    // Второй рассмотренный вариант — убрать фазу у тригона и секстиля — вернул
    // бы «Луна к твоей Луне: тема чувств» половине событий, ради которой фаза
    // и заводилась. Проверяем, что этого не сделали.
    for (const a of ['conjunction', 'opposition', 'square', 'trine', 'sextile']) {
      expect(transitTeaserText(own('Moon', a)), a).toContain('собственного цикла');
    }
  });

  it('слово «тема» остаётся: без него часть словаря не читается', () => {
    // Проверено на всех парах: «собственного цикла привычного» (Южный узел) не
    // читается, «собственного цикла слов» делает тему свойством цикла.
    expect(transitTeaserText(own('Mercury', 'trine'))).toContain('тема слов');
    expect(transitTeaserText(own('South Node', 'conjunction'))).toContain('тема привычного');
  });

  it('незнакомый аспект у своей же точки — запасной путь', () => {
    expect(transitTeaserText(own('Moon', 'quincunx'))).toBeNull();
  });

  it('трактовки нет и здесь', () => {
    const forbidden = /стоит|лучше|избегай|осторожн|удач|опасн|повезёт|получится|нужно/i;
    for (const a of ['conjunction', 'opposition', 'square', 'trine', 'sextile']) {
      expect(transitTeaserText(own('Saturn', a))).not.toMatch(forbidden);
    }
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
