# Astrea Timeline — Design System

> Источник истины для всех визуальных решений проекта. Любое отклонение от этого документа требует явного обоснования.

---

## 1. Принципы

- **Космос, не эзотерика** — глубина и точность, не мистика и символы
- **Данные первичны** — визуализация планет и транзитов важнее декора
- **Один акцент** — фиолетовый работает везде, больше акцентных цветов не добавлять
- **Тёмная тема — основная**, светлая — полноценная альтернатива, не второй сорт

---

## 2. Цветовые токены

### Тёмная тема (`.dark`, по умолчанию)

| Токен | Hex | Назначение |
|---|---|---|
| `--bg` | `#0F0A1A` | Фон страницы |
| `--bg-card` | `#1A1230` | Фон карточек |
| `--bg-deeper` | `#231C38` | Вложенные элементы, поля ввода |
| `--text-primary` | `#E2DFF0` | Основной текст |
| `--text-secondary` | `#9B97B0` | Вспомогательный текст, подписи |
| `--border` | `#2A2245` | Границы элементов |
| `--accent` | `#8B5CF6` | Акцент (кнопки, ссылки, выделения) |
| `--accent-glow` | `#A78BFA` | Свечение, hover-состояния |
| `--accent-muted` | `rgba(139,92,246,0.15)` | Фон акцентных элементов |

### Светлая тема (`:root`)

| Токен | Hex | Назначение |
|---|---|---|
| `--bg` | `#FDFBF9` | Фон страницы |
| `--bg-card` | `#FFFFFF` | Фон карточек |
| `--bg-deeper` | `#FDFBFF` | Поля ввода |
| `--text-primary` | `#1E1A2E` | Основной текст |
| `--text-secondary` | `#6B6885` | Вспомогательный текст |
| `--border` | `#EDE8F5` | Границы элементов |
| `--accent` | `#7C6CFF` | Акцент |
| `--accent-glow` | `#8B5CF6` | Hover |
| `--accent-muted` | `rgba(139,92,246,0.08)` | Фон акцентных элементов |

### Семантические цвета (оба режима)

| Токен | Тёмная | Светлая | Назначение |
|---|---|---|---|
| `--color-success` | `#34D399` | `#059669` | Успех, гармоничные аспекты |
| `--color-warning` | `#FBBF24` | `#D97706` | Предупреждение, нейтральные аспекты |
| `--color-danger` | `#F87171` | `#DC2626` | Ошибка, напряжённые аспекты |
| `--color-fire` | `#E74C3C` | `#E74C3C` | Знаки огня (Овен, Лев, Стрелец) |
| `--color-earth` | `#27AE60` | `#27AE60` | Знаки земли (Телец, Дева, Козерог) |
| `--color-air` | `#3498DB` | `#3498DB` | Знаки воздуха (Близнецы, Весы, Водолей) |
| `--color-water` | `#2980B9` | `#2980B9` | Знаки воды (Рак, Скорпион, Рыбы) |

---

## 3. Типографика

### Шрифты

```css
font-family: display — "Space Grotesk", system-ui, sans-serif  /* заголовки, кнопки, метки */
font-family: body    — "Inter", system-ui, sans-serif           /* основной текст */
```

### Шкала размеров

| Имя | Размер | Вес | Использование |
|---|---|---|---|
| `text-xs` | 11px | 700 | Метки, uppercase-подписи (letter-spacing: 0.09em) |
| `text-sm` | 13px | 400–600 | Вспомогательный текст, тосты |
| `text-base` | 16px | 400 | Основной текст, параграфы |
| `text-lg` | 18px | 500–600 | Подзаголовки карточек |
| `text-xl` | 22px | 600–700 | Заголовки секций |
| `text-2xl` | 28px | 700 | Заголовки страниц |
| `text-hero` | clamp(36px, 5vw, 58px) | 700 | Hero-заголовок (только лендинг) |

### Правила

- Метки полей — `text-xs`, `font-weight: 700`, `letter-spacing: 0.09em`, `text-transform: uppercase`, цвет `--text-secondary`
- Заголовки карточек — `text-lg` или `text-xl`, `font-family: display`
- Параграфы — `text-base`, `line-height: 1.7`, `font-family: body`
- Кнопки — `font-family: display`, `font-weight: 600–700`

---

## 4. Отступы и радиусы

### Сетка отступов (кратно 4px)

| Токен | Размер | Использование |
|---|---|---|
| `space-1` | 4px | Минимальный (между иконкой и текстом) |
| `space-2` | 8px | Внутри компонентов |
| `space-3` | 12px | Gap между элементами формы |
| `space-4` | 16px | Padding кнопок по горизонтали |
| `space-5` | 20px | Отступы внутри карточек |
| `space-6` | 24px | Gap между карточками |
| `space-8` | 32px | Отступы секций |
| `space-10` | 40px | Padding страниц |
| `space-12` | 48px | Крупные отступы |

### Радиусы скруглений

| Токен | Размер | Использование |
|---|---|---|
| `radius-sm` | 8px | Теги, бейджи |
| `radius-md` | 12px | Поля ввода, маленькие карточки |
| `radius-lg` | 16px | Кнопки, карточки |
| `radius-xl` | 20px | Большие карточки, модали |
| `radius-full` | 9999px | Аватары, круглые кнопки |

---

## 5. Компоненты

### Button

Три варианта. Высота кнопок фиксирована: `44px` (default), `36px` (sm), `52px` (lg).

**Primary**
```css
background: var(--accent);
color: #ffffff;
border-radius: radius-lg;
font-family: display; font-weight: 700;
/* hover */
background: var(--accent-glow);
/* active */
transform: scale(0.98);
```
*Motion:* hover — подъём `y: -3px` + тень `0 8px 24px rgba(139,92,246,0.32)`; tap — упругий `scale: 0.95` (spring, stiffness ~90).

**Secondary**
```css
background: var(--bg-card);
border: 1.5px solid var(--border);
color: var(--text-primary);
border-radius: radius-lg;
/* hover */
border-color: var(--accent-muted);
```
*Motion:* hover — подъём `y: -1px` + тень `0 4px 12px rgba(0,0,0,0.12)`; tap — упругий `scale: 0.97` (spring, stiffness ~90).

**Ghost**
```css
background: transparent;
border: none;
color: var(--accent);
/* hover */
background: var(--accent-muted);
```
*Motion:* без подъёма и без тени; tap — `scale: 0.98`.

**Disabled (все варианты)**
```css
opacity: 0.45;
cursor: not-allowed;
pointer-events: none;
```

---

### Card

**solid-card** — основной вариант (по умолчанию)
```css
background: var(--bg-card);
border: 1px solid var(--border);
border-radius: radius-xl;
```

**glass-card** — только когда нужен эффект прозрачности (например, поверх фонового изображения)
```css
background: color-mix(in srgb, var(--bg-card) 60%, transparent);
backdrop-filter: blur(12px);
border: 1px solid rgba(139,92,246,0.10);
border-radius: radius-xl;
```

**glow-card** — только как акцент для выделенных блоков (не по умолчанию)
```css
background: var(--bg-card);
border: 1px solid rgba(139,92,246,0.20);
border-radius: radius-xl;
box-shadow: 0 0 15px rgba(139,92,246,0.10);
```

---

### Input

```css
background: var(--bg-deeper);
border: 1.5px solid var(--border);
border-radius: radius-md;
padding: 13px 16px;
color: var(--text-primary);
font-size: 16px;
/* focus */
border-color: var(--accent);
box-shadow: 0 0 0 3px rgba(139,92,246,0.15);
outline: none;
/* error */
border-color: var(--color-danger);
```

**Label над полем**
```css
font-size: 11px; font-weight: 700;
letter-spacing: 0.09em; text-transform: uppercase;
color: var(--text-secondary);
margin-bottom: 7px;
```

---

### Badge / Tag

```css
/* default */
background: var(--accent-muted);
color: var(--accent-glow);
border-radius: radius-sm;
padding: 3px 10px;
font-size: 12px; font-weight: 600;

/* success */
background: rgba(52,211,153,0.12);
color: var(--color-success);

/* danger */
background: rgba(248,113,113,0.12);
color: var(--color-danger);
```

---

### Modal

```css
/* Overlay */
background: rgba(15,10,26,0.7);
backdrop-filter: blur(4px);

/* Dialog */
background: var(--bg-card);
border: 1px solid var(--border);
border-radius: radius-xl;
padding: space-8 space-8 space-6;
max-width: 480px;
box-shadow: 0 24px 60px rgba(0,0,0,0.4);
```

---

## 6. Тени и свечения

```css
/* Карточка — плоская тень */
box-shadow: 0 4px 20px rgba(0,0,0,0.12);

/* Glow — только как акцент на выделенных элементах, НЕ по умолчанию */
box-shadow: 0 0 15px rgba(139,92,246,0.10);

/* Модал */
box-shadow: 0 24px 60px rgba(0,0,0,0.40);
```

### Де-слоп правила (v1.1)
- **B1.** Candy-градиенты, glow-halo, radial aurora — запрещены. Фон плоский.
- **B2.** Кнопки не плоские: primary и secondary получают motion-отклик — hover-подъём (`y`) с тенью и упругий (spring) tap `scale`. Ghost — без подъёма и без тени, только tap `scale`. Цвета и заливки при этом не меняются — см. §5 Button.
- **B3.** solid-card по умолчанию. glass-card — только поверх фонового изображения.
- **B5.** Тумблер темы — SVG-глиф `stroke="currentColor"`, без эмодзи ☀️/🌙.
- **B6.** Фон dark-темы — `#0F0A1A` (deep indigo), не slate/charcoal.
- **B7.** Шрифты: Space Grotesk (заголовки, кнопки), Inter (текст). Manrope удалён.

---

## 7. Анимации

```css
/* Переходы по умолчанию */
transition: all 0.2s ease;

/* Смена темы */
transition: background-color 0.25s ease, color 0.25s ease;

/* Появление текста (SSE-стриминг) */
@keyframes fadeInChar {
  from { opacity: 0; transform: translateY(2px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* Загрузка */
@keyframes pulse-glow {
  0%, 100% { opacity: 0.4; }
  50%       { opacity: 1; }
}

/* Hover-эффект планет (NatalChart) */
transform: scale(1.2);
filter: brightness(1.3);
transition: all 0.2s ease;
```

**Правило**: `@media (prefers-reduced-motion: reduce)` — отключать все анимации кроме fade с duration 0.

---

## 8. Иконки и глифы

- Планеты — Unicode-символы (☉ ☽ ♂ ♀ ♃ ♄ ♅ ♆ ♇)
- Знаки зодиака — Unicode (♈ ♉ ♊ ♋ ♌ ♍ ♎ ♏ ♐ ♑ ♒ ♓)
- UI-иконки — SVG inline, 16×16 или 20×20
- Не использовать иконочные шрифты (Font Awesome и пр.)

---

## 9. Макет и отзывчивость

### Брейкпоинты

| Имя | Ширина | Поведение |
|---|---|---|
| `mobile` | < 768px | Одна колонка, уменьшенные отступы |
| `tablet` | 768–1024px | Две колонки |
| `desktop` | > 1024px | Полный макет |

### Ширина контента

```css
max-width: 500px;   /* формы (BirthForm) */
max-width: 700px;   /* текстовый контент, Hero */
max-width: 960px;   /* основной контент ChartPage */
max-width: 1200px;  /* широкие страницы (Admin, CRM) */
```

---

## 10. Что нельзя делать

- ❌ Добавлять новые акцентные цвета без обновления этого документа
- ❌ Хардкодить hex-значения в компонентах — только CSS-переменные
- ❌ Дублировать компоненты (TransitTimeline.jsx существует в одном месте)
- ❌ Использовать `!important`
- ❌ Смешивать inline-стили и Tailwind-классы в одном компоненте
- ❌ Создавать карточки без `border-radius` — минимум `radius-md`
- ❌ Текст светлее `--text-secondary` на тёмном фоне (контраст < 4.5:1)

---

## 11. Версионирование

| Версия | Дата | Изменения |
|---|---|---|
| 1.0 | 2026-07 | Первая версия. Зафиксированы токены, компоненты, правила. |
| 1.1 | 2026-07 | Де-слоп: плоские кнопки, solid-card по умолчанию, glow только как акцент, тумблер без эмодзи, aspect-* как отдельная шкала, токены-переменные как единый источник. |
| 1.2 | 2026-07-16 | Кнопки получили motion-отклик (подъём+тень primary/secondary, упругий tap), B2 обновлён. |
