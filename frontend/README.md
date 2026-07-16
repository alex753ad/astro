# Astrea — Frontend

## Структура

Единственный актуальный код — `frontend/src/`. Всё остальное (корневые дубли, файлы в `frontend/` вне `src`) удалено в фазе 0.

## Дизайн-токены

Единый источник токенов — **`src/index.css`** (CSS-переменные `var(--*)`).

Tailwind-палитра `brand.*` в `tailwind.config.js` **только ссылается** на эти переменные — не дублирует значения. Менять цвета нужно только в `index.css`.

### Как использовать

- В inline-стилях: `color: 'var(--accent)'`
- В Tailwind-классах: `text-brand-accent`, `bg-brand-card`, `border-brand-border`
- **Не** добавлять хардкод hex в `*.jsx` — используй токены
- Data-viz цвета (зодиак, планеты, аспекты) допустимы с комментарием `/* zodiac data-color, intentional */`

### Токены

| Переменная         | Свет         | Тёмная       | Назначение            |
|--------------------|--------------|--------------|----------------------|
| `--bg`             | #FDFBF9      | transparent  | Фон страницы         |
| `--bg-card`        | #FFFFFF      | #1A1230      | Фон карточек         |
| `--bg-deeper`      | #FDFBFF      | #231C38      | Вложенный фон        |
| `--text-primary`   | #1E1A2E      | #E2DFF0      | Основной текст       |
| `--text-secondary` | #6B6885      | #9B97B0      | Вторичный текст      |
| `--border`         | #EDE8F5      | #2A2245      | Границы              |
| `--accent`         | #7C6CFF      | #8B5CF6      | Акцент               |
| `--accent-glow`    | #8B5CF6      | #A78BFA      | Акцент hover/glow    |
| `--accent-muted`   | rgba(…,0.08) | rgba(…,0.15) | Фон акцентных зон    |

## Pre-commit hook

`frontend/scripts/no-hardcoded-hex.sh` — блокирует коммиты с новыми hex в `*.jsx`. Установка:

```bash
cp frontend/scripts/no-hardcoded-hex.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Шрифты

- **Space Grotesk** — заголовки, кнопки (`font-display`)
- **Inter** — основной текст (`font-body`)
- Manrope удалён.
