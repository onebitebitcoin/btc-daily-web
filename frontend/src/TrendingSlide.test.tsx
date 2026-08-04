import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { TrendingSlide } from './slides/TrendingSlide';
import type { Trending } from './content';

// 컴포넌트 파일(slides/TrendingSlide.tsx)에 헬퍼를 export하면 eslint의
// react-refresh/only-export-components 경고가 나므로, 테스트는 slides/ 밖에 둔다.

function buildTrending(overrides: Partial<Trending> = {}): Trending {
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
    ...overrides,
  };
}

describe('TrendingSlide', () => {
  it('renders exactly 10 rows in rank order', () => {
    const { container } = render(<TrendingSlide trending={buildTrending()} isActive onOpenTopic={() => {}} />);

    const rows = container.querySelectorAll('.trending-row');
    expect(rows).toHaveLength(10);
    expect(rows[0].querySelector('.trending-rank')?.textContent).toBe('1');
    expect(rows[9].querySelector('.trending-rank')?.textContent).toBe('10');
  });

  it('emphasizes the top 3 ranks', () => {
    const { container } = render(<TrendingSlide trending={buildTrending()} isActive onOpenTopic={() => {}} />);

    const rows = container.querySelectorAll('.trending-row');
    expect(rows[0].className).toContain('is-top');
    expect(rows[2].className).toContain('is-top');
    expect(rows[3].className).not.toContain('is-top');
  });

  it('sizes the heat bar from the item heat value', () => {
    const { container } = render(<TrendingSlide trending={buildTrending()} isActive onOpenTopic={() => {}} />);

    const firstBar = container.querySelector('.trending-row .trending-bar-fill') as HTMLElement;
    expect(firstBar.style.width).toBe('100%');
  });

  it('shows mentions and source counts as evidence figures', () => {
    const { container } = render(<TrendingSlide trending={buildTrending()} isActive onOpenTopic={() => {}} />);

    const figures = container.querySelector('.trending-figures');
    expect(figures?.textContent).toContain('10건');
    expect(figures?.textContent).toContain('5개 매체');
  });

  it('offers 펼치기 only on rows that actually have source links', () => {
    const trending = buildTrending();
    trending.items[0].links = [{ label: '토큰포스트 원문', href: 'https://a.example/1' }];

    const { container } = render(
      <TrendingSlide trending={trending} isActive onOpenTopic={() => {}} />,
    );

    const rows = container.querySelectorAll('.trending-row');
    expect(rows[0].querySelector('.trending-open')).not.toBeNull();
    expect(rows[0].querySelector('.trending-expand')?.textContent).toBe('펼치기');
    // 링크가 없는 줄까지 눌리게 하면 빈 시트가 열린다.
    expect(rows[1].querySelector('.trending-open')).toBeNull();
  });

  it('hands the clicked topic to the parent so the sheet can open', () => {
    const trending = buildTrending();
    trending.items[2].links = [{ label: 'CoinDesk 원문', href: 'https://a.example/3' }];
    const onOpenTopic = vi.fn();

    const { container } = render(
      <TrendingSlide trending={trending} isActive onOpenTopic={onOpenTopic} />,
    );
    const button = container.querySelectorAll('.trending-row')[2].querySelector(
      '.trending-open',
    ) as HTMLButtonElement;
    fireEvent.click(button);

    expect(onOpenTopic).toHaveBeenCalledTimes(1);
    expect(onOpenTopic.mock.calls[0][0].topic).toBe('토픽3');
  });

  it('omits the note paragraph when the block has none', () => {
    const { container } = render(
      <TrendingSlide trending={buildTrending({ note: null })} isActive onOpenTopic={() => {}} />,
    );

    expect(container.querySelector('.trending-note')).toBeNull();
  });
});
