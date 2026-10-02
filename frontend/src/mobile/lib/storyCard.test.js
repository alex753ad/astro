import { afterEach, describe, expect, it, vi } from 'vitest';

const share = vi.fn();
const writeFile = vi.fn(async () => ({ uri: 'file:///cache/story/a.png' }));
vi.mock('@capacitor/share', () => ({ Share: { share: (...a) => share(...a) } }));
vi.mock('@capacitor/filesystem', () => ({
  Directory: { Cache: 'CACHE' },
  Filesystem: { writeFile: (...a) => writeFile(...a) },
}));
const posted = [];
vi.mock('../../api/client', () => ({
  authFetch: async (url, init) => { posted.push([url, init?.body]); return new Response(null, { status: 204 }); },
  responseErrorText: async (_r, fallback) => fallback,
}));

const { footnote, kicker, shareStoryImage, wrapLines, STORY_URL } = await import('./storyCard');

afterEach(() => { share.mockReset(); writeFile.mockClear(); posted.length = 0; });

describe('тексты карточки дня', () => {
  it('строка даты', () => {
    expect(kicker('2026-10-01')).toBe('МОЙ ДЕНЬ · 1 ОКТЯБРЯ');
  });
  it('событие и фаза; без события — только фаза', () => {
    expect(footnote({ event: 'Луна × Венера', phase: 'убывающая Луна' })).toBe('Луна × Венера · убывающая Луна');
    expect(footnote({ event: null, phase: 'новолуние' })).toBe('новолуние');
  });
  it('перенос по словам', () => {
    const measure = (t) => t.length * 10;
    expect(wrapLines('Сегодня я радую себя', measure, 110)).toEqual(['Сегодня я', 'радую себя']);
    expect(wrapLines('Сегодняяяяяяяя', measure, 50)).toEqual(['Сегодняяяяяяяя']);
  });
  it('адрес на картинке короткий — его набирают руками', () => {
    expect(STORY_URL).toBe('aristeatime.ru/d');
  });
});

describe('отправка', () => {
  it('выбрал получателя — файл с адресом в тексте и строка счётчика', async () => {
    share.mockResolvedValue({});
    expect(await shareStoryImage('AAA', 'chart')).toBe(true);
    expect(share.mock.calls[0][0]).toMatchObject({ files: ['file:///cache/story/a.png'], text: 'https://aristeatime.ru/d' });
    expect(writeFile.mock.calls[0][0].path).toMatch(/\.png$/);
    await Promise.resolve();
    expect(posted).toEqual([[expect.stringContaining('/story-card/shared'), '{"variant":"chart"}']]);
  });
  it('закрыл лист — не ошибка и не отправка', async () => {
    share.mockRejectedValue(new Error('Share canceled'));
    expect(await shareStoryImage('AAA', 'photo')).toBe(false);
    expect(writeFile.mock.calls[0][0].path).toMatch(/\.jpg$/);
    expect(posted).toEqual([]);
  });
  it('второе нажатие, пока лист открыт, — ничего', async () => {
    let release;
    share.mockReturnValue(new Promise((r) => { release = r; }));
    const first = shareStoryImage('AAA', 'chart');
    await new Promise((r) => setTimeout(r));
    expect(await shareStoryImage('AAA', 'chart')).toBe(false);
    release({});
    expect(await first).toBe(true);
  });
});
