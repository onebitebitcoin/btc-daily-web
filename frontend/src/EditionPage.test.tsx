import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import EditionPage from './EditionPage';
import fixture from './fixtures/content.json';
import type { EditionContent } from './CardDeck';

const content = fixture as EditionContent;

function mockResponse(data: unknown, status = 200): Response {
  return { ok: status < 400, status, json: () => Promise.resolve(data) } as Response;
}

function renderEditionPage(date: string) {
  return render(
    <MemoryRouter initialEntries={[`/d/${date}`]}>
      <Routes>
        <Route path="/d/:date" element={<EditionPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('EditionPage', () => {
  it('shows a loading state, then renders the deck once data arrives', async () => {
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

    const { container } = renderEditionPage(content.meta.date);
    expect(screen.getByText('불러오는 중…')).toBeDefined();

    resolveEdition(mockResponse(content));

    await screen.findByText(content.cover.eyebrow);
    expect(container.querySelectorAll('.slide')).toHaveLength(content.cards.length + 2);
  });

  it('shows a not-found message for an unknown date', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve(url === '/api/editions' ? mockResponse([]) : mockResponse(null, 404)),
      ),
    );

    renderEditionPage('2099-01-01');
    expect(await screen.findByText('존재하지 않는 날짜입니다.')).toBeDefined();
  });
});
