import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
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
    const { container } = render(<TrendingSlide trending={buildTrending()} isActive />);

    const rows = container.querySelectorAll('.trending-row');
    expect(rows).toHaveLength(10);
    expect(rows[0].querySelector('.trending-rank')?.textContent).toBe('1');
    expect(rows[9].querySelector('.trending-rank')?.textContent).toBe('10');
  });

  it('emphasizes the top 3 ranks', () => {
    const { container } = render(<TrendingSlide trending={buildTrending()} isActive />);

    const rows = container.querySelectorAll('.trending-row');
    expect(rows[0].className).toContain('is-top');
    expect(rows[2].className).toContain('is-top');
    expect(rows[3].className).not.toContain('is-top');
  });

  it('sizes the heat bar from the item heat value', () => {
    const { container } = render(<TrendingSlide trending={buildTrending()} isActive />);

    const firstBar = container.querySelector('.trending-row .trending-bar-fill') as HTMLElement;
    expect(firstBar.style.width).toBe('100%');
  });

  it('shows mentions and source counts as evidence figures', () => {
    const { container } = render(<TrendingSlide trending={buildTrending()} isActive />);

    const figures = container.querySelector('.trending-figures');
    expect(figures?.textContent).toContain('10건');
    expect(figures?.textContent).toContain('5개 매체');
  });

  it('omits the note paragraph when the block has none', () => {
    const { container } = render(
      <TrendingSlide trending={buildTrending({ note: null })} isActive />,
    );

    expect(container.querySelector('.trending-note')).toBeNull();
  });
});
