/**
 * NebulaBackground — процедурный WebGL nebula как фиксированный фоновый слой.
 * (Содержит zodiac data-color hex: WebGL-шейдеру нужны сырые hex, не CSS-переменные.)
 * ТЗ раздел 4 («Космос»): глубокий, но не отвлекающий; u_time — медленный дрейф,
 * u_mouse — ленивый параллакс, u_accent — из --accent (#8B5CF6),
 * u_glow — сдвиг по стихии активного знака (4.2). Honors prefers-reduced-motion.
 *
 * Использование:
 *   <NebulaBackground element={hoverElement} />        // element: 'fire'|'earth'|'air'|'water'|null
 *   elementForSign('Leo') === 'fire'                    // хелпер для маппинга знака → стихия
 *
 * ВАЖНО: слой лежит на z-index:-1 под контентом. Чтобы его было видно,
 * фон страницы/карточек должен быть полупрозрачным (glass-card). См. заметку в чате.
 */

import { useRef, useEffect } from 'react';

// ── Стихии знаков ─────────────────────────────────────────
const SIGN_ELEMENT = {
  Aries: 'fire',  Leo: 'fire',    Sagittarius: 'fire',
  Taurus: 'earth', Virgo: 'earth', Capricorn: 'earth',
  Gemini: 'air',  Libra: 'air',   Aquarius: 'air',
  Cancer: 'water', Scorpio: 'water', Pisces: 'water',
};
export function elementForSign(sign) {
  return SIGN_ELEMENT[sign] || null;
}

// Цвета стихий (из DESIGN_SYSTEM, оба режима одинаковые)
/* zodiac data-color, intentional — WebGL shader needs raw hex, not CSS vars */
const ELEMENT_COLORS = {
  fire:  '#E74C3C',
  earth: '#27AE60',
  air:   '#3498DB',
  water: '#2980B9',
};

function hexToRgb(hex) {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map(c => c + c).join('') : h, 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

const VERT = `
attribute vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }
`;

const FRAG = `
precision highp float;
uniform float u_time;
uniform vec2  u_resolution;
uniform vec2  u_mouse;
uniform vec3  u_accent;
uniform vec3  u_glow;
uniform float u_intensity;

float hash(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float noise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  float a = hash(i), b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0)), d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}
float fbm(vec2 p){
  float v = 0.0, a = 0.5;
  mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
  for (int i = 0; i < 5; i++) { v += a * noise(p); p = m * p; a *= 0.5; }
  return v;
}
void main(){
  vec2 uv = gl_FragCoord.xy / u_resolution.xy;
  float aspect = u_resolution.x / u_resolution.y;
  vec2 p = uv; p.x *= aspect;

  vec2 par = (u_mouse - 0.5) * 0.15;      // ленивый параллакс
  float t = u_time * 0.02;                 // медленный дрейф

  vec2 q = vec2(fbm(p * 2.0 + t + par), fbm(p * 2.0 - t + par + 5.2));
  float n = fbm(p * 3.0 + q * 2.0 + par);
  n = smoothstep(0.2, 0.9, n);
  float density = pow(n, 1.6);

  vec3 base = vec3(0.04, 0.02, 0.09);
  vec3 col = mix(base, u_accent, density * 0.9);
  col += u_glow * pow(density, 3.0) * 0.6;

  float stars = step(0.997, hash(floor(gl_FragCoord.xy / 2.0)));
  col += stars * 0.5;

  float vig = smoothstep(1.2, 0.3, length(uv - 0.5));
  col *= vig * u_intensity;

  gl_FragColor = vec4(col, 1.0);
}
`;

function compile(gl, type, src) {
  const sh = gl.createShader(type);
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    console.error('[nebula] shader:', gl.getShaderInfoLog(sh));
    gl.deleteShader(sh);
    return null;
  }
  return sh;
}

export default function NebulaBackground({
  accentColor = '#8B5CF6', /* zodiac data-color, intentional — WebGL needs raw hex */
  element = null,
  intensity = 1.0,
}) {
  const canvasRef = useRef(null);
  // Мутабельные цели для плавной интерполяции без ре-рендера
  const state = useRef({
    mouse: [0.5, 0.5], mouseTarget: [0.5, 0.5],
    glow: hexToRgb(accentColor), glowTarget: hexToRgb(accentColor),
    accent: hexToRgb(accentColor), intensity,
  });

  // Обновляем цели при смене пропсов
  useEffect(() => {
    const s = state.current;
    s.accent = hexToRgb(accentColor);
    s.glowTarget = element && ELEMENT_COLORS[element]
      ? hexToRgb(ELEMENT_COLORS[element])
      : hexToRgb(accentColor);
    s.intensity = intensity;
  }, [accentColor, element, intensity]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (!gl) return; // нет WebGL — просто нет фона

    const prog = gl.createProgram();
    const vs = compile(gl, gl.VERTEX_SHADER, VERT);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'a_pos');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    const U = {
      time:       gl.getUniformLocation(prog, 'u_time'),
      resolution: gl.getUniformLocation(prog, 'u_resolution'),
      mouse:      gl.getUniformLocation(prog, 'u_mouse'),
      accent:     gl.getUniformLocation(prog, 'u_accent'),
      glow:       gl.getUniformLocation(prog, 'u_glow'),
      intensity:  gl.getUniformLocation(prog, 'u_intensity'),
    };

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width  = Math.floor(window.innerWidth  * dpr);
      canvas.height = Math.floor(window.innerHeight * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
    }
    resize();
    window.addEventListener('resize', resize);

    function onMove(e) {
      state.current.mouseTarget = [e.clientX / window.innerWidth, 1 - e.clientY / window.innerHeight];
    }
    window.addEventListener('mousemove', onMove);

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let raf = 0;
    const start = performance.now();

    function frame(now) {
      const s = state.current;
      // ленивая интерполяция мыши и glow
      s.mouse[0] += (s.mouseTarget[0] - s.mouse[0]) * 0.04;
      s.mouse[1] += (s.mouseTarget[1] - s.mouse[1]) * 0.04;
      for (let i = 0; i < 3; i++) s.glow[i] += (s.glowTarget[i] - s.glow[i]) * 0.05;

      gl.uniform1f(U.time, reduce ? 0 : (now - start) / 1000);
      gl.uniform2f(U.resolution, canvas.width, canvas.height);
      gl.uniform2f(U.mouse, s.mouse[0], s.mouse[1]);
      gl.uniform3fv(U.accent, s.accent);
      gl.uniform3fv(U.glow, s.glow);
      gl.uniform1f(U.intensity, s.intensity);
      gl.drawArrays(gl.TRIANGLES, 0, 3);

      // при reduced-motion glow/мышь всё ещё могут доезжать — но без дрейфа времени.
      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', onMove);
      const ext = gl.getExtension('WEBGL_lose_context');
      if (ext) ext.loseContext();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      style={{
        position: 'fixed', inset: 0, width: '100%', height: '100%',
        zIndex: -1, pointerEvents: 'none', display: 'block',
      }}
    />
  );
}
