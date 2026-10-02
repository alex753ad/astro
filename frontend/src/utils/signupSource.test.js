import { describe, it, expect } from 'vitest';
import { sourceFromSearch } from './signupSource';

describe('sourceFromSearch', () => {
  it('метки редиректа /d', () => {
    expect(sourceFromSearch('?utm_source=story&utm_medium=share&utm_campaign=day_card'))
      .toBe('story/share/day_card');
  });
  it('без utm_source — ничего', () => {
    expect(sourceFromSearch('?ref=abc')).toBeNull();
  });
  it('нижний регистр и не длиннее 64', () => {
    expect(sourceFromSearch('?utm_source=VK')).toBe('vk//');
    expect(sourceFromSearch(`?utm_source=${'a'.repeat(100)}`)).toHaveLength(64);
  });
});
