import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ShortsFeed } from './ShortsFeed';
import fixture from './fixtures/content.json';
import type { EditionContent, Trending } from './content';

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

// fixtures/content.json에는 trending을 넣지 않는다(백엔드 테스트가 이 파일을 "trending
// 없이도 동작" 기준 페이로드로 쓴다) — 그래서 여기서 직접 만든다.
function trendingBlock(): Trending {
  return {
    eyebrow: '24H TRENDING',
    title: '지난 24시간 가장 뜨거웠던 토픽',
    note: '뉴스 20건 · 유튜브 5건 집계',
    items: Array.from({ length: 10 }, (_, i) => ({
      rank: i + 1,
      topic: `토픽${i + 1}`,
      heat: 100 - i * 8,
      mentions: 10 - i,
      sources: 5 - Math.floor(i / 3),
    })),
  };
}

function editionWithTrendingFor(date: string): EditionContent {
  return { ...editionFor(date), trending: trendingBlock() };
}

function stubApiWithTrending() {
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
        json: () => Promise.resolve(editionWithTrendingFor(date)),
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

  it('never rewrites the address bar while scrolling', async () => {
    // 스크롤이 주소를 바꾸면 `/`에서 북마크한 링크가 그날 날짜에 고정돼버린다.
    stubApi();
    const replaceState = vi.spyOn(window.history, 'replaceState');
    const pushState = vi.spyOn(window.history, 'pushState');
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);

    fireEvent.keyDown(window, { key: 'ArrowDown' });
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    await waitFor(() =>
      expect(container.querySelectorAll('.slide')[2].className).toContain('is-active'),
    );

    expect(replaceState).not.toHaveBeenCalled();
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

  it('renders 12 slides (no trending slide) when the edition lacks a trending block', async () => {
    stubApi();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);

    expect(container.querySelectorAll('.slide')).toHaveLength(SLIDES_PER_EDITION);
    expect(container.querySelector('.trending-list')).toBeNull();
  });

  it('inserts a trending slide (13 total) right before closing when the edition has one', async () => {
    stubApiWithTrending();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);

    expect(container.querySelectorAll('.slide')).toHaveLength(SLIDES_PER_EDITION + 1);

    const slides = Array.from(container.querySelectorAll('.slide'));
    const trendingIndex = slides.findIndex((s) => s.querySelector('.trending-list'));
    const closingIndex = slides.findIndex((s) => s.querySelector('.is-closing'));
    expect(trendingIndex).toBeGreaterThan(-1);
    expect(closingIndex).toBe(trendingIndex + 1);
  });

  it('renders all 10 trending rows on the trending slide', async () => {
    stubApiWithTrending();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);

    expect(container.querySelectorAll('.trending-row')).toHaveLength(10);
  });
});
