import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { DIGEST_TIERS, showsDigestDay } from './digestAccess';

describe('showsDigestDay', () => {
  it('только Лира и Орион', () => {
    expect(showsDigestDay('pro')).toBe(true);
    expect(showsDigestDay('premium')).toBe(true);
    expect(showsDigestDay('free')).toBe(false);
    expect(showsDigestDay('lite')).toBe(false);
    expect(showsDigestDay(undefined)).toBe(false);
  });

  it('совпадает с фильтром рассылки в backend/tasks.py', () => {
    const src = readFileSync(fileURLToPath(new URL('../../../../backend/tasks.py', import.meta.url)), 'utf-8');
    const fn = src.slice(src.indexOf('def send_weekly_digest_task'));
    const m = /User\.tier\.in_\(\[([^\]]*)\]\)/.exec(fn);
    expect(m).not.toBeNull();
    const server = [...m[1].matchAll(/"(\w+)"/g)].map((x) => x[1]);
    expect(server.sort()).toEqual([...DIGEST_TIERS].sort());
  });
});
