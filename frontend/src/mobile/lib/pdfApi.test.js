import { describe, expect, it } from 'vitest';
import { pdfFileName } from './pdfApi';

describe('имя файла PDF в приложении', () => {
  it('по имени карты, без символов, запрещённых в пути', () => {
    expect(pdfFileName('Анна')).toBe('Натальная карта — Анна.pdf');
    expect(pdfFileName('a/b:c')).toBe('Натальная карта — abc.pdf');
    expect(pdfFileName(null)).toBe('Натальная карта.pdf');
  });
});
