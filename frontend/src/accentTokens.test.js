/**
 * accentTokens.test.js — сторож пары «hex ↔ компоненты» у акцента.
 *
 * Зачем пара вообще. Прозрачность от токена нужна в 106 местах
 * (`rgba(var(--accent-rgb), .15)`). Взять её из `--accent` напрямую нечем:
 * единственный способ — `color-mix(in srgb, var(--accent) 15%, transparent)`,
 * а он требует Chrome 111+ (2023). При `minSdkVersion 23` и на устройствах без
 * сервисов Google WebView не обновляется — там объявление молча отбрасывается,
 * цвет пропадает, и на десктопе разработчика этого не видно вовсе (тот же класс
 * отказа, что у астрологических значков и у `Preferences`-Proxy в CLAUDE.md).
 * Поэтому компоненты лежат отдельным токеном.
 *
 * ⚠️ Что сломается без этого теста: `--accent` и `--accent-rgb` — ДВА места
 * одного цвета. Правка одного без второго не падает и ничего не подсвечивает:
 * сплошные заливки уедут на новый цвет, а все полупрозрачные (рамки, тени,
 * фоны чипов) останутся на старом. Интерфейс станет двухцветным, и заметить
 * это можно только глазами, сравнив сплошное с прозрачным. В этом проекте
 * пары уже расходились так (письма про PDF против TIER_FLAGS), поэтому
 * инвариант закреплён, а не оставлен на внимательность.
 *
 * Проверяются ОБА файла: index.css (веб) и mobile/mobile.css (приложение).
 * Значения между файлами не сверяются — это разные источники истины по
 * решению владельца (DESIGN_SYSTEM.md §1); здесь только внутренняя
 * согласованность каждого.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const here = dirname(fileURLToPath(import.meta.url));

const FILES = {
  'index.css': resolve(here, 'index.css'),
  'mobile/mobile.css': resolve(here, 'mobile/mobile.css'),
};

const stripComments = (css) => css.replace(/\/\*[\s\S]*?\*\//g, '');

/**
 * Тело правила по точному селектору — разбором по скобкам, а не регуляркой.
 * Регулярка тут дороже: селектор `.dark` встречается и как часть составных
 * (`.dark .tt-scope`), и её пришлось бы городить с отрицательными проверками.
 */
function block(css, selector) {
  const clean = stripComments(css);
  const lines = clean.split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    if (lines[i].trim() !== selector + ' {') continue;
    const out = [];
    for (let j = i + 1; j < lines.length; j += 1) {
      if (lines[j].trim() === '}') return out.join('\n');
      out.push(lines[j]);
    }
  }
  return null;
}

function decl(body, name) {
  for (const line of body.split('\n')) {
    const at = line.indexOf('--' + name + ':');
    if (at === -1) continue;
    const rest = line.slice(at + name.length + 3);
    const end = rest.indexOf(';');
    return (end === -1 ? rest : rest.slice(0, end)).trim();
  }
  return null;
}

function hexToRgb(hex) {
  const m = hex.trim().match(/^#([0-9a-fA-F]{6})$/);
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

const parseTriple = (s) => s.split(',').map((x) => Number(x.trim()));

const PAIRS = [
  ['accent', 'accent-rgb'],
  ['accent-glow', 'accent-glow-rgb'],
];

describe('токены акцента: hex и компоненты описывают один цвет', () => {
  for (const [label, path] of Object.entries(FILES)) {
    const css = readFileSync(path, 'utf8');

    for (const selector of [':root', '.dark']) {
      const themeName = selector === ':root' ? 'светлая' : 'тёмная';
      const body = block(css, selector);

      it(`${label} · ${themeName} · блок ${selector} найден`, () => {
        expect(body).toBeTruthy();
      });

      for (const [hexName, rgbName] of PAIRS) {
        it(`${label} · ${themeName} · --${hexName} === --${rgbName}`, () => {
          const hex = decl(body, hexName);
          const triple = decl(body, rgbName);
          expect(hex, `нет --${hexName}`).toBeTruthy();
          expect(triple, `нет --${rgbName}`).toBeTruthy();

          const fromHex = hexToRgb(hex);
          expect(fromHex, `--${hexName} не шестизначный hex: ${hex}`).toBeTruthy();
          expect(parseTriple(triple)).toEqual(fromHex);
        });
      }
    }
  }
});

describe('числовой акцент остался только в объявлении --*-rgb', () => {
  // Пара обязана быть ЕДИНСТВЕННЫМ местом, где эти три цвета записаны числами.
  // Вернувшийся литерал rgba(...) значит, что кто-то снова прописал цвет мимо
  // токена — то есть палитра опять меняется не в одном месте.
  const LITERAL = /rgba\(\s*(?:139\s*,\s*92\s*,\s*246|124\s*,\s*108\s*,\s*255|167\s*,\s*139\s*,\s*250)\s*,/g;

  for (const [label, path] of Object.entries(FILES)) {
    it(`${label} — литералов rgba() нет`, () => {
      const css = stripComments(readFileSync(path, 'utf8'));
      expect(css.match(LITERAL)).toBeNull();
    });
  }
});
