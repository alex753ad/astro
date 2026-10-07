import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/**
 * Ловушка: запросы с Bearer — только через authFetch.
 *
 * Access-токен живёт 15 минут. Голый fetch() с токеном из localStorage через
 * 15 минут получает 401 и не обновляется — PDF, ссылка, карточка, позиции
 * транзитов молча ломаются, пока человек не перезагрузит страницу.
 * authFetch (api/client.js) обновляет токен и повторяет запрос; свой
 * заголовок Authorization он перекрывает свежим, поэтому chartAuthHeaders()
 * и X-Chart-Token в options можно передавать как есть.
 *
 * Список файлов растёт по мере перевода (roadmap, «Голые fetch»).
 */
const FILES = [
  "../pages/ChartPage.jsx",
  "../components/TransitTimeline.jsx",
  "../components/RagChat.jsx",
];

describe("нет голого fetch в файлах с авторизацией", () => {
  for (const rel of FILES) {
    it(rel, () => {
      const src = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
      const bare = src
        .split("\n")
        .filter((l) => !l.trim().startsWith("//") && /(^|[^\w.])fetch\(/.test(l));
      expect(bare).toEqual([]);
    });
  }
});
