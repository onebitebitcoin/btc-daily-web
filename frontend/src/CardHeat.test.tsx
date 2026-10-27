import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CardSlide } from './slides/CardSlide';
import { cardTrend, type Card, type Trending, type TrendingItem } from './content';

function buildCard(overrides: Partial<Card> = {}): Card {
  return {
    num: 4,
    chip: null,
    title: '제목',
    subtitle: 'Subtitle',
    chips_label: null,
    chips: null,
    body: '본문',
    quote: null,
    link: null,
    media: null,
    ...overrides,
  };
}

const TREND: TrendingItem = { rank: 2, topic: '오픈AI', heat: 64, mentions: 9, sources: 8 };

function trendingWith(items: TrendingItem[]): Trending {
  return { eyebrow: '24H TRENDING', title: '토픽', note: null, items };
}

function renderSlide(card: Card, trend: TrendingItem | null) {
  return render(
    <CardSlide
      card={card}
      date="2026-10-27"
      total={10}
      media={{}}
      isActive
      shouldLoadImage
      onOpenDetail={() => {}}
      likeCount={0}
      liked={false}
      onToggleLike={() => {}}
      onShare={() => {}}
      trend={trend}
    />,
  );
}

describe('카드 화제성 줄', () => {
  it('트렌딩에 걸린 카드는 순위·토픽·매체 수와 heat 길이 막대를 보인다', () => {
    const { container } = renderSlide(buildCard({ trend_rank: 2 }), TREND);

    expect(screen.getByText('TRENDING 2위 · 오픈AI')).toBeTruthy();
    expect(screen.getByText('8개 매체')).toBeTruthy();
    const fill = container.querySelector<HTMLElement>('.card-heat .trending-bar-fill');
    expect(fill?.style.width).toBe('64%');
  });

  it('트렌딩에 안 걸린 지정 뉴스는 막대 없이 지정 뉴스 표시만 보인다', () => {
    const { container } = renderSlide(buildCard({ pinned: true }), null);

    expect(screen.getByText('지정 뉴스')).toBeTruthy();
    expect(container.querySelector('.card-heat .trending-bar-track')).toBeNull();
  });

  it('트렌딩에도 안 걸리고 지정 뉴스도 아닌 카드는 줄 자체를 그리지 않는다', () => {
    const { container } = renderSlide(buildCard(), null);

    expect(container.querySelector('.card-heat')).toBeNull();
  });
});

describe('cardTrend', () => {
  const trending = trendingWith([
    { rank: 1, topic: '앤트로픽', heat: 100, mentions: 13, sources: 13 },
    TREND,
  ]);

  it('카드의 trend_rank 와 같은 순위의 트렌딩 항목을 돌려준다', () => {
    expect(cardTrend(buildCard({ trend_rank: 2 }), trending)).toEqual(TREND);
  });

  it('trend_rank 가 없거나 트렌딩 블록이 없으면 null 이다', () => {
    expect(cardTrend(buildCard(), trending)).toBeNull();
    expect(cardTrend(buildCard({ trend_rank: 2 }), null)).toBeNull();
    expect(cardTrend(buildCard({ trend_rank: 2 }), undefined)).toBeNull();
  });

  it('가리킨 순위가 트렌딩에 없으면 null 이다', () => {
    expect(cardTrend(buildCard({ trend_rank: 7 }), trending)).toBeNull();
  });
});
