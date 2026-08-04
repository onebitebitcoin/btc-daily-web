import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import EditionPage, { LatestFeed } from './EditionPage';
import fixture from './fixtures/content.json';
import type { EditionContent } from './content';

const content = fixture as EditionContent;

function mockResponse(data: unknown, status = 200): Response {
  return { ok: status < 400, status, json: () => Promise.resolve(data) } as Response;
}

function renderEditionPage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/d/:date" element={<EditionPage />} />
        <Route path="/d/:date/:index" element={<EditionPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('EditionPage', () => {
  it('shows a loading state, then renders the feed once data arrives', async () => {
    let resolveEdition!: (res: Response) => void;
    const editionResponse = new Promise<Response>((resolve) => {
      resolveEdition = resolve;
    });
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        url === '/api/editions' ? Promise.resolve(mockResponse([])) : editionResponse,
      ),
    );

    const { container } = renderEditionPage(`/d/${content.meta.date}`);
    expect(screen.getByText('불러오는 중…')).toBeDefined();

    resolveEdition(mockResponse(content));

    await screen.findByText(content.cover.eyebrow);
    expect(container.querySelectorAll('.slide')).toHaveLength(content.cards.length + 2);
  });

  it('shows the not-found message on its own slide for an unknown date', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve(url === '/api/editions' ? mockResponse([]) : mockResponse(null, 404)),
      ),
    );

    renderEditionPage('/d/2099-01-01');

    expect(await screen.findByText('존재하지 않는 날짜입니다.')).toBeDefined();
  });

  it('rejects a malformed date in the path', () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(mockResponse([]))));

    renderEditionPage('/d/not-a-date');

    expect(screen.getByText('잘못된 경로입니다.')).toBeDefined();
  });

  it('accepts a card deep link without crashing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve(url === '/api/editions' ? mockResponse([]) : mockResponse(content)),
      ),
    );

    const { container } = renderEditionPage(`/d/${content.meta.date}/3`);

    await screen.findByText(content.cover.eyebrow);
    expect(container.querySelectorAll('.slide')).toHaveLength(content.cards.length + 2);
  });
});

function renderLatestFeed() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<LatestFeed />} />
        <Route path="/d/:date" element={<EditionPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('LatestFeed', () => {
  it('shows a no-data message when no edition has ever been published', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(mockResponse([]))));

    renderLatestFeed();

    expect(await screen.findByText('아직 발행된 데이터가 없습니다.')).toBeDefined();
  });

  it('starts at the newest edition and leaves the URL on /', async () => {
    // `/d/{최신}`으로 리다이렉트하면 거기서 북마크한 링크가 그 날짜에 고정된다.
    const list = [
      { date: '2026-07-29', slug: 'a', title: 'a' },
      { date: content.meta.date, slug: 'b', title: 'b' },
    ];
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve(url === '/api/editions' ? mockResponse(list) : mockResponse(content)),
      ),
    );

    const { container } = renderLatestFeed();

    await screen.findByText(content.cover.eyebrow);
    expect(container.querySelector('.date-chip')?.textContent).toContain('07.30');
  });

  it('learns the newest date from the list instead of downloading a whole edition', async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        calls.push(url);
        return Promise.resolve(
          url === '/api/editions'
            ? mockResponse([{ date: content.meta.date, slug: 'b', title: 'b' }])
            : mockResponse(content),
        );
      }),
    );

    renderLatestFeed();

    await screen.findByText(content.cover.eyebrow);
    expect(calls).not.toContain('/api/editions/latest');
  });

  it('surfaces a network failure instead of hanging on the loading state', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('offline'))));

    renderLatestFeed();

    expect(await screen.findByText('서버에 연결할 수 없습니다.')).toBeDefined();
  });
});
