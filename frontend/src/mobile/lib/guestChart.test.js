import { beforeEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { clearGuestChart, getGuestChart, guestHeaders, isGuest, setGuestChart } from './guestChart';
import { buildChartPayload } from './chartCreateRules';

function memoryStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
  };
}

const future = () => new Date(Date.now() + 86400000).toISOString();

beforeEach(() => { globalThis.localStorage = memoryStorage(); });

describe('карта гостя', () => {
  it('гость — карта есть, входа нет', () => {
    expect(isGuest()).toBe(false);
    setGuestChart({ id: 'c1', token: 't1', expiresAt: future() });
    expect(isGuest()).toBe(true);
    localStorage.setItem('astro_access_token', 'jwt');
    expect(isGuest()).toBe(false);
  });

  it('просроченная карта забывается: лента ответила бы 404', () => {
    setGuestChart({ id: 'c1', token: 't1', expiresAt: new Date(Date.now() - 1000).toISOString() });
    expect(getGuestChart()).toBeNull();
    expect(localStorage.getItem('aristea_guest_chart')).toBeNull();
  });

  it('токен карты уходит только к запросам про эту карту', () => {
    setGuestChart({ id: 'c1', token: 't1', expiresAt: future() });
    expect(guestHeaders('https://x/api/v1/chart/c1/feed?from_date=1')).toEqual({ 'X-Chart-Token': 't1' });
    expect(guestHeaders('https://x/api/v1/chart/c1/claim')).toEqual({ 'X-Chart-Token': 't1' });
    expect(guestHeaders('https://x/api/v1/chart/other/feed')).toEqual({});
    expect(guestHeaders('https://x/api/v1/feedback')).toEqual({});
    clearGuestChart();
    expect(guestHeaders('https://x/api/v1/chart/c1/feed')).toEqual({});
  });

  it('согласие уходит в запросе, только если дано', () => {
    const form = { birthDate: '1990-06-15', birthPlace: 'Москва' };
    expect(buildChartPayload(form)).not.toHaveProperty('consent');
    expect(buildChartPayload({ ...form, consent: true }).consent).toBe(true);
  });
});

// Рендер-тестов нет (ни jsdom, ни testing-library) — связь с экранами по
// исходнику, как в feedAnchor.test.js.
describe('экраны у гостя', () => {
  const read = (p) => readFileSync(fileURLToPath(new URL(p, import.meta.url)), 'utf-8');

  it('лента: закрытые события и карточка горизонта гостю не показываются, полоса планет — вся', () => {
    const src = read('../screens/FeedScreen.jsx');
    expect(src).toMatch(/const allEvents = feed\?\.events \|\| \[\];/);
    expect(src).toMatch(/!\(guest && e\.locked\)\)/);
    expect(src).toMatch(/\{!guest && <FeedHorizonCard/);
  });

  it('подсказки «Карты» сами не открываются, у всех', () => {
    expect(read('../screens/ChartScreen.jsx')).toMatch(/useHints\('chart', [^)]*\{ auto: false \}\)/);
  });

  it('приветствие строит карту в приложении, а не на сайте', () => {
    const src = read('../screens/WelcomeScreen.jsx');
    expect(src).toMatch(/navigate\('\/guest\/new'/);
    expect(src).not.toMatch(/openInBrowser\(/);
  });

  it('форма гостя без галочки не отправляется', () => {
    expect(read('../components/ChartCreateView.jsx')).toMatch(/disabled=\{busy \|\| \(guest && !consent\)\}/);
  });
});
