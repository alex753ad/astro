/**
 * wheelPng.js — снимок колеса (NatalChart, svg#natal-chart-svg) в PNG base64
 * для PDF. Вынесено из ChartPage.jsx 29.09.2026, когда снимок понадобился
 * приложению: без картинки сервер рисует упрощённое колесо
 * (natal_pdf._wheel — без домов, осей и раздвижки близких планет).
 * CRMPage.jsx держит свою прежнюю копию — не переведена.
 *
 * Значки планет в снимке рисуются шрифтом AstroSymbols, встроенным в <style>
 * самого SVG как data: URI (NatalChart.jsx, `?inline`). SVG, открытый как
 * <img>, внешних ресурсов не грузит — с обычным url() на Android вместо
 * значков были бы пустые прямоугольники (src/assets/fonts/README.md).
 * ⚠️ Проверять снимок только на сборке (`vite build` + `preview`): в dev
 * `?inline` отдаёт ссылку `/src/assets/fonts/…`, а не data: URI, и знаки
 * зодиака в снимке выходят emoji-квадратиками — дефект стенда, не кода
 * (проверено 29.09.2026 headless Chrome на картах Коли и Анны).
 */

// Резолвит var(--...) в fill/stroke/stop-color в реальные цвета, читая computed
// style с ЖИВОГО узла: сериализованный отдельно SVG (Blob → <img>) не видит стили
// документа, var(--...) не резолвится и атрибут откатывается к initial — для fill
// это чёрный. Отсюда чёрный круг колеса в захваченном PNG.
function resolveSvgVarColors(liveEl, cloneEl) {
  for (const prop of ['fill', 'stroke', 'stop-color']) {
    const val = cloneEl.getAttribute(prop);
    if (val && val.includes('var(')) {
      const resolved = getComputedStyle(liveEl).getPropertyValue(prop);
      if (resolved) cloneEl.setAttribute(prop, resolved.trim());
    }
  }
  const liveChildren = liveEl.children;
  const cloneChildren = cloneEl.children;
  for (let i = 0; i < liveChildren.length; i++) {
    resolveSvgVarColors(liveChildren[i], cloneChildren[i]);
  }
}

// ── Захват SVG колеса в прозрачный PNG (base64) — общая утилита ──
async function captureSvgPng(svgId, size = 1200) {
  const svg = document.getElementById(svgId);
  if (!svg) return null;
  try {
    const clone = svg.cloneNode(true);
    resolveSvgVarColors(svg, clone);
    const svgData = new XMLSerializer().serializeToString(clone);
    const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);
    const img = new Image();
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = url; });
    const cvs = document.createElement('canvas');
    cvs.width = size;
    cvs.height = size;
    const ctx = cvs.getContext('2d');
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, size, size);
    ctx.drawImage(img, 0, 0, size, size);
    URL.revokeObjectURL(url);
    return cvs.toDataURL('image/png').split(',')[1];
  } catch {
    return null;
  }
}

// Переключает NatalChart в светлую тему, ждёт ре-рендер, захватывает PNG, возвращает в исходную тему
export async function captureChartPng(setForExport, size = 1200) {
  setForExport(true);
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const png = await captureSvgPng('natal-chart-svg', size);
  setForExport(false);
  return png;
}
