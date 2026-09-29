import { afterEach, describe, expect, it, vi } from 'vitest';

const share = vi.fn();
const openFile = vi.fn();
vi.mock('@capacitor/share', () => ({ Share: { share: (...a) => share(...a) } }));
vi.mock('@capawesome-team/capacitor-file-opener', () => ({ FileOpener: { openFile: (...a) => openFile(...a) } }));
vi.mock('@capacitor/filesystem', () => ({
  Directory: { Cache: 'CACHE' },
  Filesystem: { writeFile: async () => ({ uri: 'file:///cache/pdf/a.pdf' }) },
}));
const posted = [];
vi.mock('./authFetchTimeout', () => ({
  authFetchWithTimeout: async (url, init) => {
    if (init?.method === 'POST') { posted.push(JSON.parse(init.body)); return new Response('{"status":"queued"}'); }
    return new Response(new Blob(['%PDF']), { status: 200 });
  },
  getWithRetry: vi.fn(),
}));

// Окружение тестов — node, FileReader там нет.
vi.stubGlobal('FileReader', class {
  readAsDataURL() { this.result = 'data:application/pdf;base64,JVBERg=='; setTimeout(() => this.onload()); }
});

const { errorText, openPdf, pdfFileName, sharePdf, startPdf } = await import('./pdfApi');

afterEach(() => { share.mockReset(); openFile.mockReset(); });

describe('имя файла PDF в приложении', () => {
  it('по имени карты, без символов, запрещённых в пути', () => {
    expect(pdfFileName('Анна')).toBe('Натальная карта — Анна.pdf');
    expect(pdfFileName('a/b:c')).toBe('Натальная карта — abc.pdf');
    expect(pdfFileName(null)).toBe('Натальная карта.pdf');
  });
});

describe('ошибки PDF — только по-русски', () => {
  it('английский текст плагина заменяется, русский текст сервера проходит', () => {
    expect(errorText(new Error("Can't share while sharing is in progress"), 'X')).toBe('X');
    expect(errorText(new Error('Лимит PDF на этот месяц исчерпан'), 'X')).toBe('Лимит PDF на этот месяц исчерпан');
    expect(errorText(null, 'X')).toBe('X');
  });
});

describe('открыть и поделиться', () => {
  it('«Открыть» отдаёт файл читалке как PDF', async () => {
    expect(await openPdf('r1', 'Анна')).toBe(true);
    expect(openFile).toHaveBeenCalledWith({ path: 'file:///cache/pdf/a.pdf', mimeType: 'application/pdf' });
    expect(share).not.toHaveBeenCalled();
  });

  it('пока лист «Поделиться» открыт, повторное нажатие ничего не делает', async () => {
    let close;
    share.mockImplementation(() => new Promise((r) => { close = r; }));
    const first = sharePdf('r1', 'Анна');
    await vi.waitFor(() => expect(share).toHaveBeenCalledTimes(1));
    expect(await sharePdf('r1', 'Анна')).toBe(false);
    expect(await openPdf('r1', 'Анна')).toBe(false);
    expect(share).toHaveBeenCalledTimes(1);
    close();
    expect(await first).toBe(true);
    expect(await openPdf('r1', 'Анна')).toBe(true);   // после закрытия — снова можно
  });

  it('закрыть лист без выбора — не ошибка', async () => {
    share.mockRejectedValue(new Error('Share canceled'));
    expect(await sharePdf('r1', 'Анна')).toBe(true);
  });
});

describe('сборка PDF', () => {
  it('снимок колеса уходит на сервер; без него — null, сервер рисует своё', async () => {
    await startPdf('c1', 'iVBOR');
    await startPdf('c1');
    expect(posted).toEqual([{ wheel_png: 'iVBOR' }, { wheel_png: null }]);
  });
});
