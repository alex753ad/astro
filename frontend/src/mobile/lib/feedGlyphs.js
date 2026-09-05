/**
 * feedGlyphs.js — астрологические значки планет и точек.
 *
 * Нужны в двух местах ленты: полоса «сейчас» показывает планету значком
 * (§4), свёрнутая строка лунных — значки натальных точек, по которым Луна
 * прошла (§7).
 *
 * ⚠️ Эти символы НЕЛЬЗЯ рисовать системным шрифтом. На Android и iOS
 * покрытие блока Unicode Misc Symbols то пустое (в ленте будут пустые
 * прямоугольники-тофу), то подменяется цветным emoji-шрифтом, который
 * игнорирует `color` и рисует картинку вместо знака. Ровно по этой причине
 * веб уже носит с собой сабсет Noto Sans Symbols — см.
 * src/assets/fonts/README.md. Мобильная сборка подключает ТЕ ЖЕ два файла
 * через @font-face в mobile.css (семейство `AstroSymbols`), поэтому здесь
 * достаточно строкового значка, а стиль его накладывает потребитель.
 *
 * Два файла, а не один: ☉ Солнце (U+2609) лежит только в Noto Sans
 * Symbols 2, остальное — в первом. Это свойство шрифтов, а не наша
 * прихоть.
 *
 * Ключи — английские имена планет, как их отдаёт ручка (`meta.planet` в
 * нижнем регистре у планера, `meta.natal_planet` с заглавной у транзитов),
 * поэтому поиск идёт без учёта регистра.
 */

const GLYPHS = {
  sun: '☉',        // ☉
  moon: '☽',       // ☽
  mercury: '☿',    // ☿
  venus: '♀',      // ♀
  mars: '♂',       // ♂
  jupiter: '♃',    // ♃
  saturn: '♄',     // ♄
  uranus: '♅',     // ♅
  neptune: '♆',    // ♆
  pluto: '♇',      // ♇
  'north node': '☊', // ☊
  'south node': '☋', // ☋
};

/** Значок планеты или точки. Пустая строка — если значка нет. */
export function glyph(planet) {
  if (!planet) return '';
  return GLYPHS[String(planet).toLowerCase()] || '';
}

/**
 * Стиль для значка. Семейство обязано идти первым, а запасное — системное:
 * если шрифт почему-то не доехал, знак хотя бы попробует отрисоваться, а не
 * исчезнет.
 */
export const glyphStyle = {
  fontFamily: 'AstroSymbols, system-ui, sans-serif',
  lineHeight: 1,
};

/**
 * Символы аспектов и их цвет (§4 SPEC_FEED_VISUAL.md) — карточка транзита
 * показывает фактуру аспекта цветом, а не словом «Оппозиция».
 *
 * Символы — обычная пунктуация/математические знаки (□, △, ✶), кроме ☌/☍,
 * которые лежат в том же блоке Misc Symbols, что и планеты, — поэтому
 * формула целиком идёт шрифтом AstroSymbols (glyphStyle), не только планеты.
 */
const ASPECT_SYMBOLS = {
  conjunction: '☌',
  opposition: '☍',
  square: '□',
  trine: '△',
  sextile: '✶',
};

export function aspectSymbol(aspectType) {
  return ASPECT_SYMBOLS[aspectType] || '·';
}

/**
 * Цвет аспекта: трин/секстиль — гармоничный (`--color-success`), квадрат/
 * оппозиция — напряжённый (`--color-danger`), соединение — нейтральный
 * (`--text-primary`): оно само по себе не бывает ни тем ни другим, смысл
 * задаёт контекст, которого в карточке-фактуре нет.
 */
export function aspectColor(aspectType) {
  if (aspectType === 'trine' || aspectType === 'sextile') return 'var(--color-success)';
  if (aspectType === 'square' || aspectType === 'opposition') return 'var(--color-danger)';
  return 'var(--text-primary)';
}
