import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ShortsFeed } from './ShortsFeed';
import fixture from './fixtures/content.json';
import type { EditionContent, Trending } from './content';

const base = fixture as EditionContent;
const DATES = ['2026-07-28', '2026-07-29', '2026-07-30'];

/** 브라우저를 최소한으로 흉내낸다 — 스크롤이 일어나면 그 슬라이드가 보이게 된다.
 *
 *  jsdom 에는 IntersectionObserver 도 스크롤도 없다. 스텁이 없으면 useVerticalFeed 의
 *  관찰자 경로가 통째로 꺼져 실제 브라우저에 존재하지 않는 상태로 테스트가 돈다.
 *  그 상태에서는 이동 잠금이 관찰자 확인 대신 타임아웃으로만 풀려 테스트가 느려진다.
 */
function stubScrollObserver() {
  const callbacks = new Set<(entries: unknown[]) => void>();
  const targets = new WeakSet<Element>();

  class FakeIntersectionObserver {
    constructor(private cb: (entries: unknown[]) => void) {
      callbacks.add(cb);
    }
    observe(el: Element) {
      targets.add(el);
    }
    disconnect() {
      callbacks.delete(this.cb);
    }
  }
  vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);

  // 스크롤이 시작되면 그 슬라이드가 화면을 채웠다고 알린다.
  Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
    if (!targets.has(this)) return;
    const entry = { target: this, isIntersecting: true, intersectionRatio: 1 };
    callbacks.forEach((cb) => cb([entry]));
  });
}

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

/** 한 칸 내려가고 실제로 반영될 때까지 기다린다.
 *
 *  키를 그냥 연달아 쏘면 안 된다. useVerticalFeed 는 앞 이동이 정착할 때까지 새 요청을
 *  버리므로, 잠금이 아직 걸려 있는 동안 쏜 키는 그대로 사라진다. 로컬에서는 빨라서
 *  우연히 통과하고 느린 CI 러너에서 깨졌다(2026-09-18, 매번 다른 테스트가 걸렸다).
 *
 *  그래서 이동 버튼이 다시 살아나는 것을 보고 나서 누른다. 버튼의 disabled 가 곧 잠금
 *  상태이므로(FeedNav 의 busy), 이 대기가 "입력을 받을 수 있는 시점"을 정확히 집는다.
 */
async function advance(container: HTMLElement, to: number) {
  const downButton = () =>
    container.querySelector('button[aria-label="다음 카드"]') as HTMLButtonElement | null;

  await waitFor(() => expect(downButton()?.disabled).toBe(false), { timeout: 3000 });
  fireEvent.click(downButton()!);

  // 실제 브라우저는 스무스 스크롤이 멎으면 scrollend 를 준다. 그게 와야 잠금이 풀려
  // 다음 이동이 열린다. jsdom 에는 이 이벤트가 없으므로 손으로 쏜다(enableScrollEnd).
  const track = container.querySelector('.feed-track');
  if (track) act(() => void track.dispatchEvent(new Event('scrollend')));

  await waitFor(
    () => expect(container.querySelectorAll('.slide')[to]?.className).toContain('is-active'),
    { timeout: 3000 },
  );
}

async function advanceTo(container: HTMLElement, target: number) {
  for (let i = 1; i <= target; i += 1) await advance(container, i);
}

/** `'onscrollend' in window` 를 통과시켜 지원 브라우저 경로를 밟게 한다.
 *  jsdom 은 이 이벤트를 구현하지 않아서, 심지 않으면 리스너가 붙지 않는다. */
function enableScrollEnd() {
  (window as { onscrollend?: unknown }).onscrollend = null;
}

beforeEach(() => {
  stubScrollObserver();
  enableScrollEnd();
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete (window as { onscrollend?: unknown }).onscrollend;
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
    await advanceTo(container, SLIDES_PER_EDITION - 3);

    await waitFor(() =>
      expect(container.querySelectorAll('.slide').length).toBeGreaterThan(SLIDES_PER_EDITION),
    );
    expect(await screen.findByText('2026-07-29')).toBeDefined();
  });

  it('marks the second edition cover as a date break', async () => {
    stubApi();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);

    await advanceTo(container, SLIDES_PER_EDITION - 3);

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

    await advanceTo(container, 3);

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

    await advanceTo(container, 2);

    expect(replaceState).not.toHaveBeenCalled();
    expect(pushState).not.toHaveBeenCalled();
  });

  it('opens the detail sheet', async () => {
    stubApi();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);

    fireEvent.click(screen.getAllByText('더보기')[0]);

    expect(container.querySelector('.sheet')).not.toBeNull();
  });

  it('closes the detail sheet on Escape', async () => {
    stubApi();
    const { container } = renderFeed();
    await screen.findByText(base.cover.eyebrow);
    fireEvent.click(screen.getAllByText('더보기')[0]);

    fireEvent.keyDown(document, { key: 'Escape' });

    await waitFor(() => expect(container.querySelector('.sheet')).toBeNull());
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
