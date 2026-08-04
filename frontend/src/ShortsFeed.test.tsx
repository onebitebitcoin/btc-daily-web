import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ShortsFeed } from './ShortsFeed';
import fixture from './fixtures/content.json';
import type { EditionContent } from './content';

const base = fixture as EditionContent;
const DATES = ['2026-07-28', '2026-07-29', '2026-07-30'];

function editionFor(date: string): EditionContent {
  return {
    ...base,
    meta: { ...base.meta, date },
    cover: { ...base.cover, mark: [date] },
  };
}

function stubApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string) => {
      if (path === '/api/editions') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(DATES.map((d) => ({ date: d, slug: d, title: d }))),
        } as Response);
      }
      const date = path.replace('/api/editions/', '');
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(editionFor(date)),
      } as Response);
    }),
  );
}

function renderFeed(startDate = '2026-07-30', startIndex = 0) {
  return render(
    <MemoryRouter initialEntries={[`/d/${startDate}`]}>
      <ShortsFeed startDate={startDate} startIndex={startIndex} />
    </MemoryRouter>,
  );
}

const SLIDES_PER_EDITION = base.cards.length + 2;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ShortsFeed', () => {
  it('renders one slide per card plus cover and closing', async () => {
    stubApi();
    const { container } = renderFeed();

    await screen.findByText(base.cover.eyebrow);

    expect(container.querySelectorAll('.slide')).toHaveLength(SLIDES_PER_EDITION);
  });

  it('appends the previous date so the feed continues past the closing card', async () => {
    stubApi();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);

    // 끝에서 두 칸 앞까지 내려가면 다음 날짜가 붙는다.
    for (let i = 0; i < SLIDES_PER_EDITION; i += 1) {
      fireEvent.keyDown(window, { key: 'ArrowDown' });
    }

    await waitFor(() =>
      expect(container.querySelectorAll('.slide').length).toBeGreaterThan(SLIDES_PER_EDITION),
    );
    expect(await screen.findByText('2026-07-29')).toBeDefined();
  });

  it('marks the second edition cover as a date break', async () => {
    stubApi();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);

    for (let i = 0; i < SLIDES_PER_EDITION; i += 1) {
      fireEvent.keyDown(window, { key: 'ArrowDown' });
    }

    await waitFor(() => expect(container.querySelector('.is-date-break')).not.toBeNull());
    expect(container.querySelector('.date-break-rule')?.textContent).toContain('2026-07-29');
  });

  it('only loads images within a small window of the current slide', async () => {
    stubApi();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);

    // 현재 인덱스 ±2 창이라 커버 + 카드1..2 = 최대 3장.
    const loaded = container.querySelectorAll('.art img');
    expect(loaded.length).toBeLessThanOrEqual(3);
    expect(loaded.length).toBeGreaterThan(0);
  });

  it('loads more images as the reader advances, not all at once', async () => {
    stubApi();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);
    const atStart = container.querySelectorAll('.art img').length;

    fireEvent.keyDown(window, { key: 'ArrowDown' });
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    fireEvent.keyDown(window, { key: 'ArrowDown' });

    await waitFor(() => {
      const nowLoaded = container.querySelectorAll('.art img').length;
      expect(nowLoaded).toBeLessThanOrEqual(atStart + 3);
    });
    expect(container.querySelectorAll('.art img').length).toBeLessThan(base.cards.length);
  });

  it('keeps the address bar in sync without stacking history entries', async () => {
    stubApi();
    const replaceState = vi.spyOn(window.history, 'replaceState');
    const pushState = vi.spyOn(window.history, 'pushState');
    renderFeed();
    await screen.findByText(base.cover.eyebrow);

    fireEvent.keyDown(window, { key: 'ArrowDown' });

    await waitFor(() =>
      expect(replaceState).toHaveBeenCalledWith(null, '', '/d/2026-07-30/1'),
    );
    expect(pushState).not.toHaveBeenCalled();
  });

  it('opens the detail sheet and locks the feed behind it', async () => {
    stubApi();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);

    fireEvent.click(screen.getAllByText('더보기')[0]);

    expect(container.querySelector('.sheet')).not.toBeNull();
    expect(container.querySelector('.feed-track.is-locked')).not.toBeNull();
  });

  it('closes the detail sheet on Escape and unlocks the feed', async () => {
    stubApi();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);
    fireEvent.click(screen.getAllByText('더보기')[0]);

    fireEvent.keyDown(document, { key: 'Escape' });

    await waitFor(() => expect(container.querySelector('.sheet')).toBeNull());
    expect(container.querySelector('.feed-track.is-locked')).toBeNull();
  });

  it('does not move the feed while the sheet is open', async () => {
    stubApi();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);
    fireEvent.click(screen.getAllByText('더보기')[0]);

    fireEvent.keyDown(window, { key: 'ArrowDown' });

    expect(container.querySelectorAll('.slide')[0].className).toContain('is-active');
  });

  it('shows the progress bar for the current edition only', async () => {
    stubApi();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);

    expect(container.querySelectorAll('.progress-bar i')).toHaveLength(SLIDES_PER_EDITION);
  });

  it('opens a calendar sheet from the date chip', async () => {
    stubApi();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);

    fireEvent.click(container.querySelector('[aria-label="날짜 선택"]') as Element);

    expect(container.querySelector('.cal-sheet')).not.toBeNull();
  });
});
