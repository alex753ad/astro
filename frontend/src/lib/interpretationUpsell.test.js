import { describe, it, expect } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { TIER_WORDS, interpretationUpsell } from "./interpretationUpsell";

/**
 * Синхронность обещанного объёма разбора между фронтендом и бэкендом.
 *
 * Зачем этот тест существует. Кнопка приписки под разбором говорит «НА 2500
 * СЛОВ» — это обещание, и число живёт в двух местах, в разных языках:
 *
 *   - `lib/interpretationUpsell.js` — `PRO_WORDS`, единственный источник на
 *     фронте: по нему набирается кнопка и в вебе (`Interpretation.jsx`), и в
 *     приложении (`mobile/components/InterpretView.jsx`);
 *   - `auth/rate_limits.py` — `TIER_FLAGS["pro"]["interpretation_word_limit"]`,
 *     по которому сервер реально просит объём у модели.
 *
 * До 09.09.2026 фронтовая половина была ЛИТЕРАЛОМ прямо в кнопке, и связи с
 * бэкендом у неё не было никакой. Литерал вынесен в константу при появлении
 * второго потребителя (экран разбора в приложении) — иначе копий числа стало
 * бы три.
 *
 * Два числа, обязанные совпадать, в разных языках и без общего источника —
 * ровно та конструкция, которая в этом проекте уже расходилась: письмо Лиры
 * обещало 5 PDF при `pdf_per_month = 15`, письмо Веги — транзиты на 12
 * месяцев при `transits_months = 1`. Разойдутся здесь — человек заплатит за
 * Лиру, увидев на кнопке одно число, и получит другое. Молча: обе половины
 * по отдельности останутся «правильными».
 *
 * ⚠️ Тест НЕ закрепляет само значение 2500. Владелец вправе сменить объём на
 * Лире — тогда правится флаг, и тест обязан позеленеть от одной этой правки.
 * Он стережёт РАВЕНСТВО, а не число.
 *
 * Тест читает исходники, а не мокает: проверять надо согласованность двух
 * половин, а не поведение одной из них. Тот же приём и та же причина, что в
 * `api/transitsHorizon.test.js`.
 */

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const read = (p) => readFileSync(repoRoot + p, "utf-8");

const BACKEND = "backend/auth/rate_limits.py";
const WEB = "frontend/src/components/Interpretation.jsx";
const MOBILE = "frontend/src/mobile/components/InterpretView.jsx";

/** Границы блока тарифа в rate_limits.py — по порядку объявления TIER_FLAGS. */
const TIER_BOUNDS = { lite: ['"lite": {', '"pro": {'], pro: ['"pro": {', '"premium": {'] };

/** Значение TIER_FLAGS[tier]["interpretation_word_limit"] из rate_limits.py. */
function backendWords(tier) {
  const src = read(BACKEND);
  const [from, to] = TIER_BOUNDS[tier];
  const block = src.slice(src.indexOf(from), src.indexOf(to));
  const m = block.match(/"interpretation_word_limit":\s*(\d+)/);
  expect(m, `в ${BACKEND} не найден interpretation_word_limit у ${tier}`).not.toBeNull();
  return Number(m[1]);
}

describe("объём разбора на Лире: кнопка и сервер обещают одно и то же", () => {
  it("TIER_WORDS совпадает с interpretation_word_limit на бэкенде — оба тарифа", () => {
    expect(TIER_WORDS.pro).toBe(backendWords("pro"));
    expect(TIER_WORDS.lite).toBe(backendWords("lite"));
  });

  it("числа попадают в текст, а не теряются по дороге", () => {
    // Без этого равенство выше можно было бы удержать, случайно перестав
    // показывать число человеку, — и тест продолжил бы зеленеть.
    expect(interpretationUpsell("lite").cta).toContain(String(backendWords("pro")));
    expect(interpretationUpsell("free").text).toContain(String(backendWords("lite")));
  });

  it("величины не нулевые — иначе текст обещает пустоту", () => {
    expect(backendWords("pro")).toBeGreaterThan(0);
    expect(backendWords("lite")).toBeGreaterThan(0);
  });

  it("веб берёт текст из общего файла, а не набирает своим литералом", () => {
    // Литерал здесь означал бы возврат к состоянию до 09.09.2026: число в
    // кнопке ничем не связано с сервером и расходится незаметно.
    const src = read(WEB);
    expect(src).toContain("interpretationUpsell");
    expect(src).not.toMatch(/НА\s*\d+\s*СЛОВ/);
  });

  it("приложение берёт оттуда же — третьей копии числа нет", () => {
    // ⚠️ Проверка условная, и это не поблажка. Экран разбора живёт в ветке
    // interpret-mobile, ещё не влитой в main: серверная половина этой пары
    // едет на прод раньше и ждать приёмки экрана не должна. Как только
    // ветка приедет, файл появится и проверка включится сама — молчать она
    // будет ровно до этого момента, а не всегда.
    if (!existsSync(repoRoot + MOBILE)) {
      expect(existsSync(repoRoot + WEB), "веб-половина обязана быть на месте").toBe(true);
      return;
    }
    const src = read(MOBILE);
    expect(src).toContain("interpretationUpsell");
    expect(src).not.toMatch(/НА\s*\d+\s*СЛОВ/);
  });

  it("на фронте числа объявлены один раз", () => {
    // Ровно один экспорт: вторая таблица с тем же смыслом — начало того же
    // расхождения, только внутри фронтенда.
    const src = read("frontend/src/lib/interpretationUpsell.js");
    expect(src.match(/^export const TIER_WORDS\s*=/gm) || []).toHaveLength(1);
  });

  it("ни одно из чисел не набрано в тексте литералом", () => {
    // Смысл всей конструкции: правка флага на бэкенде обязана менять текст,
    // а не расходиться с ним молча.
    const src = read("frontend/src/lib/interpretationUpsell.js");
    const body = src.slice(src.indexOf("export function interpretationUpsell"));
    expect(body).not.toMatch(/(800|2500)/);
  });
});

describe("зовём в соседний тариф, а не через один", () => {
  it("free зовут в Вегу, а не сразу в Лиру", () => {
    // Решение владельца 09.09.2026. До этого free предлагали перепрыгнуть с
    // 0 ₽ на 2490 ₽ мимо тарифа за 790 ₽ — самый дорогой шаг из возможных и
    // единственный названный.
    const free = interpretationUpsell("free");
    expect(free.text).toContain("Вега");
    expect(free.text).not.toContain("Лира");
  });

  it("lite зовут в Лиру", () => {
    expect(interpretationUpsell("lite").subtitle).toContain("Лира");
  });

  it("названное в тексте число принадлежит тому тарифу, в который зовут", () => {
    // Иначе free увидит объём Лиры под именем Веги — обещание чужого тарифа.
    expect(interpretationUpsell("free").text).toContain(String(backendWords("lite")));
    expect(interpretationUpsell("free").text).not.toContain(String(backendWords("pro")));
  });
});

describe("кому показываем приписку", () => {
  it("pro и premium не получают ничего", () => {
    // Предлагать более глубокий разбор тому, у кого он самый глубокий, —
    // способ выглядеть навязчивым и глупым разом.
    expect(interpretationUpsell("pro")).toBeNull();
    expect(interpretationUpsell("premium")).toBeNull();
  });

  it("free и отсутствующий тариф получают одно и то же", () => {
    // Пока тариф не приехал, показать предложение безопаснее, чем показать
    // пустоту тому, кто уже заплатил. Так же считает веб (isFree).
    expect(interpretationUpsell("free")).toEqual(interpretationUpsell(undefined));
    expect(interpretationUpsell("free").kind).toBe("free");
  });

  it("lite получает свой баннер, а не free-приписку", () => {
    expect(interpretationUpsell("lite").kind).toBe("lite");
  });
});
