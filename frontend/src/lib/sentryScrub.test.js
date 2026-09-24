import { describe, it, expect } from 'vitest';
import { scrubEvent } from './sentryScrub';

describe('scrubEvent', () => {
  it('не пропускает дату и место рождения, тексты чата и email', () => {
    const out = scrubEvent({
      user: { id: 'u1', email: 'a@b.ru' },
      request: {
        url: 'https://localhost/chart?place=Москва',
        query_string: 'place=Москва',
        data: { birth_date: '1990-06-15', birth_place: 'Москва' },
      },
      breadcrumbs: [
        { category: 'fetch', data: { url: 'https://aristeatime.ru/api/v1/geo?q=Москва', method: 'GET' } },
        { category: 'console', message: 'ответ: 1990-06-15 Москва' },
        { category: 'ui.click', message: 'button «Что меня ждёт?»' },
      ],
      message: 'ошибка для a@b.ru',
      exception: { values: [{ value: 'Email send failed for a@b.ru' }] },
    });
    const flat = JSON.stringify(out);
    for (const secret of ['Москва', '1990-06-15', 'a@b.ru', 'Что меня ждёт']) {
      expect(flat).not.toContain(secret);
    }
    expect(out.breadcrumbs).toHaveLength(1);
    expect(out.breadcrumbs[0].data.url).toBe('https://aristeatime.ru/api/v1/geo');
    expect(out.breadcrumbs[0].data.method).toBe('GET');
  });
});
