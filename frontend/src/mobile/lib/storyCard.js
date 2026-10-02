/**
 * storyCard.js — карточка дня для сторис (флаг story_card, решение владельца
 * 01.10.2026). Что написать — сервер (backend/story_card.py), картинку рисует
 * устройство на <canvas> и отдаёт в системный лист «Поделиться» тем же путём,
 * что и PDF (pdfApi.js): файл в кеш приложения → @capacitor/share.
 *
 * Два варианта на выбор человека (наброски утверждены владельцем 01.10.2026,
 * палитра «атлас»):
 *   · chart — «Моя карта»: колесо с фигурой аспектов, фраза, дата, адрес;
 *   · photo — «На своё фото»: плашка-наклейка поверх фото из галереи.
 *     Наклейка вшивается в картинку, а не отдаётся отдельным слоем:
 *     отдельный слой умеет только Instagram и только через App ID Meta —
 *     от этого владелец отказался 01.10.2026; ВКонтакте не умеет вовсе.
 *
 * ⚠️ Адрес на картинке — единственная ссылка, которая доживёт до сторис:
 * Instagram и ВКонтакте берут из «Поделиться» только картинку. Поэтому он
 * короткий (/d, редирект с метками — nginx astreatime.conf) и печатается.
 *
 * ⚠️ Фиолетовый — только литера «A»; дата и линии — золото (решение
 * владельца 01.10.2026: фиолетовое свечение выглядело «картинкой нейросети»).
 */
import { API_BASE } from '../../config';
import { authFetch, responseErrorText } from '../../api/client';
import { once } from './shareOnce';

export const STORY_CARD_FLAG = 'story_card';
export const STORY_URL = 'aristeatime.ru/d';
export const FAIL_TEXT = 'Не получилось собрать картинку, попробуй ещё раз';

const W = 1080;
const H = 1920;
export const ATLAS = {
  bg: '#0F1A33',
  line: '#D9B56A',
  text: '#F3E9D2',
  muted: '#AFA58F',
  mark: '#B9A0F5',
};
const SERIF = 'Literata';
const SANS = '"Golos Text"';
const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
  'августа', 'сентября', 'октября', 'ноября', 'декабря'];

export async function fetchStoryCard(chartId, date) {
  const r = await authFetch(`${API_BASE}/chart/${chartId}/story-card?date=${date}`);
  if (!r.ok) throw new Error(await responseErrorText(r, FAIL_TEXT));
  return r.json();
}

/** Счётчик отправок — best-effort: картинка уже ушла, ошибка тут не важна. */
export function markShared(variant) {
  authFetch(`${API_BASE}/story-card/shared`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ variant }),
  }).catch(() => {});
}

/** «МОЙ ДЕНЬ · 1 ОКТЯБРЯ» из «2026-10-01». */
export function kicker(isoDate) {
  const [, m, d] = isoDate.split('-').map(Number);
  return `Мой день · ${d} ${MONTHS[m - 1]}`.toUpperCase();
}

/** «Луна × Венера · убывающая Луна»; без события — только фаза. */
export function footnote(card) {
  return [card.event, card.phase].filter(Boolean).join(' · ');
}

/** Перенос по словам в ширину. measure(text) → ширина в пикселях. */
export function wrapLines(text, measure, maxWidth) {
  const lines = [];
  let line = '';
  for (const word of text.split(' ')) {
    const next = line ? `${line} ${word}` : word;
    if (line && measure(next) > maxWidth) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines;
}

/** Самый крупный кегль из sizes, при котором фраза встаёт в maxLines строк. */
export function fitPhrase(ctx, text, maxWidth, sizes, maxLines = 2) {
  for (const size of sizes) {
    ctx.font = `500 ${size}px ${SERIF}`;
    const lines = wrapLines(text, (t) => ctx.measureText(t).width, maxWidth);
    if (lines.length <= maxLines) return { size, lines };
  }
  const size = sizes[sizes.length - 1];
  ctx.font = `500 ${size}px ${SERIF}`;
  return { size, lines: wrapLines(text, (t) => ctx.measureText(t).width, maxWidth) };
}

// Шрифты приложения подгружаются по требованию (@font-face в mobile.css,
// разные файлы для кириллицы и латиницы). Canvas сам их не дождётся и
// нарисует запасным шрифтом — грузим явно, с текстом в обоих алфавитах.
async function loadFonts() {
  const sample = 'Мой день aristeatime';
  await Promise.all([
    document.fonts.load(`500 96px ${SERIF}`, sample),
    document.fonts.load(`600 32px ${SANS}`, sample),
    document.fonts.load(`400 34px ${SANS}`, sample),
  ]).catch(() => {});
}

function canvas2d() {
  const c = document.createElement('canvas');
  c.width = W;
  c.height = H;
  return [c, c.getContext('2d')];
}

/** Литера «A» (src/assets/aristea-a.svg, viewBox 56) размером size. */
function drawMark(ctx, x, y, size, color) {
  const k = size / 56;
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(k, k);
  ctx.strokeStyle = color;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.lineWidth = 3.6;
  ctx.beginPath();
  ctx.moveTo(15, 42); ctx.lineTo(28, 15); ctx.lineTo(41, 42);
  ctx.stroke();
  ctx.lineWidth = 3.2;
  ctx.beginPath();
  ctx.moveTo(21, 31); ctx.lineTo(35, 31);
  ctx.stroke();
  ctx.restore();
}

/** Литера и адрес одной строкой, по центру cx (или от левого края, align='left'). */
function drawAddress(ctx, x, y, size, color, align = 'center') {
  ctx.font = `400 ${size}px ${SANS}`;
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'left';
  const mark = size * 1.3;
  const gap = size * 0.4;
  const total = mark + gap + ctx.measureText(STORY_URL).width;
  const left = align === 'center' ? x - total / 2 : x - total;
  drawMark(ctx, left, y - mark / 2, mark, ATLAS.mark);
  ctx.fillStyle = color;
  ctx.fillText(STORY_URL, left + mark + gap, y);
}

function drawWheel(ctx, figure, cx, cy) {
  const R1 = 420; const R2 = 384; const R3 = 250;
  // Как на утверждённом наброске: x = cx + r·cos, y = cy − r·sin.
  const pt = (deg, r) => {
    const t = (deg * Math.PI) / 180;
    return [cx + r * Math.cos(t), cy - r * Math.sin(t)];
  };
  ctx.save();
  ctx.strokeStyle = ATLAS.line;
  ctx.fillStyle = ATLAS.line;
  ctx.lineWidth = 1.6;
  ctx.beginPath(); ctx.arc(cx, cy, R1, 0, Math.PI * 2); ctx.stroke();
  ctx.globalAlpha = 0.7;
  ctx.beginPath(); ctx.arc(cx, cy, R3, 0, Math.PI * 2); ctx.stroke();
  // 72 деления по 5°, каждое шестое — длинное. Ни к знакам, ни к домам не
  // привязаны: колесо повёрнуто сервером (story_card.figure).
  for (let k = 0; k < 72; k += 1) {
    const inner = k % 6 === 0 ? R2 : (k % 2 === 0 ? R1 - 12 : R1 - 7);
    ctx.globalAlpha = k % 6 === 0 ? 1 : 0.55;
    const [x1, y1] = pt(k * 5, R1);
    const [x2, y2] = pt(k * 5, inner);
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  }
  const pts = (figure?.points || []).map((a) => pt(a, R3));
  ctx.lineWidth = 1.3;
  ctx.globalAlpha = 0.85;
  for (const [i, j] of figure?.lines || []) {
    ctx.beginPath(); ctx.moveTo(...pts[i]); ctx.lineTo(...pts[j]); ctx.stroke();
  }
  ctx.globalAlpha = 1;
  for (const [x, y] of pts) {
    ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill();
  }
  ctx.restore();
}

/** «Моя карта» — 1080×1920, PNG base64 без префикса. */
export async function drawChartCard(card) {
  await loadFonts();
  const [c, ctx] = canvas2d();
  ctx.fillStyle = ATLAS.bg;
  ctx.fillRect(0, 0, W, H);
  // Сверху ~300 px пусто: там интерфейс сторис (имя, полоска времени).
  drawWheel(ctx, card.figure, W / 2, 740);

  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillStyle = ATLAS.line;
  ctx.font = `600 32px ${SANS}`;
  ctx.letterSpacing = '6px';
  ctx.fillText(kicker(card.date), W / 2, 1250);
  ctx.letterSpacing = '0px';

  const { size, lines } = fitPhrase(ctx, card.phrase, 920, [96, 84, 72]);
  ctx.fillStyle = ATLAS.text;
  let y = 1320;
  for (const line of lines) {
    ctx.fillText(line, W / 2, y);
    y += size * 1.1;
  }

  ctx.font = `400 34px ${SANS}`;
  ctx.fillStyle = ATLAS.muted;
  ctx.fillText(footnote(card), W / 2, y + 40);
  // Низ ~230 px тоже пуст: там строка ответа в сторис.
  drawAddress(ctx, W / 2, 1668, 34, ATLAS.muted);
  return c.toDataURL('image/png').split(',')[1];
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/** «На своё фото» — фото на весь кадр (обрезка по центру) и плашка. */
export async function drawPhotoCard(card, image) {
  await loadFonts();
  const [c, ctx] = canvas2d();
  const iw = image.width; const ih = image.height;
  const k = Math.max(W / iw, H / ih);
  ctx.drawImage(image, (W - iw * k) / 2, (H - ih * k) / 2, iw * k, ih * k);

  const x = 120; const w = 840; const pad = 56;
  const phrase = fitPhrase(ctx, card.phrase, w - pad * 2, [80, 72, 64]);
  const h = 46 + 34 + 18 + phrase.lines.length * phrase.size * 1.08 + 30 + 34 + 40;
  const y = Math.min(1110, H - 260 - h);   // над строкой ответа сторис

  ctx.fillStyle = 'rgba(15, 26, 51, 0.94)';
  roundRect(ctx, x, y, w, h, 36);
  ctx.fill();
  ctx.strokeStyle = 'rgba(217, 181, 106, 0.55)';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillStyle = ATLAS.line;
  ctx.font = `600 28px ${SANS}`;
  ctx.letterSpacing = '5px';
  ctx.fillText(kicker(card.date), W / 2, y + 46);
  ctx.letterSpacing = '0px';

  ctx.font = `500 ${phrase.size}px ${SERIF}`;
  ctx.fillStyle = ATLAS.text;
  let ty = y + 46 + 34 + 18;
  for (const line of phrase.lines) {
    ctx.fillText(line, W / 2, ty);
    ty += phrase.size * 1.08;
  }

  const fy = ty + 30 + 17;
  ctx.font = `400 28px ${SANS}`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = ATLAS.muted;
  ctx.fillText(card.event || card.phase, x + pad, fy);
  drawAddress(ctx, x + w - pad, fy, 28, ATLAS.muted, 'right');
  return c.toDataURL('image/jpeg', 0.92).split(',')[1];
}

/** Файл из галереи → картинка для canvas. Поворот по EXIF WebView делает сам. */
export function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Не получилось открыть фото')); };
    img.src = url;
  });
}

/**
 * Картинка → кеш → системный лист. true — человек выбрал, куда отправить
 * (тогда же пишется счётчик); false — закрыл лист или уже идёт другой вызов.
 */
export async function shareStoryImage(base64, variant) {
  let sent = false;
  const ran = await once(async () => {
    const { Filesystem, Directory } = await import('@capacitor/filesystem');
    const ext = variant === 'photo' ? 'jpg' : 'png';
    const { uri } = await Filesystem.writeFile({
      path: `story/aristea-moy-den.${ext}`, data: base64, directory: Directory.Cache, recursive: true,
    });
    const { Share } = await import('@capacitor/share');
    try {
      // Текст доходит только до мессенджеров; в сторис ссылку несёт картинка.
      await Share.share({ files: [uri], text: `https://${STORY_URL}`, dialogTitle: 'Поделиться днём' });
      sent = true;
    } catch (e) {
      if (!/cancel/i.test(String(e?.message || e))) throw e;
    }
  });
  if (ran && sent) markShared(variant);
  return ran && sent;
}
