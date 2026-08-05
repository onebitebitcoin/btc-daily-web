import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { CardArt } from './CardArt';
import { CardSlide } from './slides/CardSlide';
import { showsSubtitleInBody } from './artText';
import type { Card } from './content';

function buildCard(overrides: Partial<Card> = {}): Card {
  return {
    num: 4,
    chip: { text: '자기보관', emphasis: 'secondary' },
    title: '개발자들이 자기보관 수칙을 다시 쓰기 시작했다',
    subtitle: 'Rewriting Self-Custody Rules',
    chips_label: null,
    chips: ['#자기보관'],
    body: '본문',
    quote: '지갑을 바꾸는 게 아니라 습관을 바꿔야 한다는 결론이다.',
    link: null,
    media: null,
    ...overrides,
  };
}

const DATE = '2026-08-05';

describe('CardArt 대체 아트', () => {
  it('이미지가 없는 카드는 빈 자리 대신 인용을 조판한다', () => {
    const { container } = render(
      <CardArt card={buildCard()} date={DATE} media={{}} shouldLoad />,
    );

    const art = container.querySelector('.art-type');
    expect(art).not.toBeNull();
    expect(art?.textContent).toContain('지갑을 바꾸는 게 아니라 습관을 바꿔야 한다는 결론이다.');
  });

  it('인용이 없으면 영문 부제로 대체한다', () => {
    const { container } = render(
      <CardArt card={buildCard({ quote: null })} date={DATE} media={{}} shouldLoad />,
    );

    expect(container.querySelector('.art-type')?.textContent).toContain(
      'Rewriting Self-Custody Rules',
    );
  });

  it('인용도 부제도 없으면 분류 칩으로 대체한다', () => {
    const { container } = render(
      <CardArt card={buildCard({ quote: null, subtitle: null })} date={DATE} media={{}} shouldLoad />,
    );

    expect(container.querySelector('.art-type')?.textContent).toContain('자기보관');
  });

  it('쓸 문구가 하나도 없으면 카드 번호로 떨어진다', () => {
    const { container } = render(
      <CardArt
        card={buildCard({ quote: null, subtitle: null, chip: null })}
        date={DATE}
        media={{}}
        shouldLoad
      />,
    );

    expect(container.querySelector('.art-type')).toBeNull();
    expect(container.querySelector('.art-blank')?.textContent).toBe('04');
  });

  it('인용일 때만 따옴표를 세우고, 화면 낭독에서는 감춘다', () => {
    const quoted = render(<CardArt card={buildCard()} date={DATE} media={{}} shouldLoad />);
    const mark = quoted.container.querySelector('.art-type-mark');
    expect(mark).not.toBeNull();
    expect(mark?.getAttribute('aria-hidden')).toBe('true');

    const labelled = render(
      <CardArt card={buildCard({ quote: null })} date={DATE} media={{}} shouldLoad />,
    );
    expect(labelled.container.querySelector('.art-type-mark')).toBeNull();
  });

  it('연달아 나와도 같아 보이지 않게 카드 번호로 톤을 돌린다', () => {
    const seven = render(<CardArt card={buildCard({ num: 7 })} date={DATE} media={{}} shouldLoad />);
    const eight = render(<CardArt card={buildCard({ num: 8 })} date={DATE} media={{}} shouldLoad />);

    const toneOf = (c: HTMLElement) => c.querySelector('.art-type')?.className.match(/tone-\d/)?.[0];
    expect(toneOf(seven.container)).toBeDefined();
    expect(toneOf(seven.container)).not.toBe(toneOf(eight.container));
  });

  it('아트가 부제를 가져가면 본문에서는 같은 줄을 빼 메아리를 없앤다', () => {
    const noQuote = buildCard({ quote: null });
    expect(showsSubtitleInBody(noQuote)).toBe(false);

    const { container } = render(
      <CardSlide
        card={noQuote}
        date={DATE}
        total={10}
        media={{}}
        isActive
        shouldLoadImage
        onOpenDetail={() => {}}
      />,
    );

    const shown = container.querySelectorAll('.card-body .secondary');
    expect(shown).toHaveLength(0);
    expect(container.querySelector('.art-type')?.textContent).toContain(
      'Rewriting Self-Custody Rules',
    );
  });

  it('아트가 인용을 쓰면 본문 부제는 그대로 남는다', () => {
    const withQuote = buildCard();
    expect(showsSubtitleInBody(withQuote)).toBe(true);

    const { container } = render(
      <CardSlide
        card={withQuote}
        date={DATE}
        total={10}
        media={{}}
        isActive
        shouldLoadImage
        onOpenDetail={() => {}}
      />,
    );

    expect(container.querySelector('.card-body .secondary')?.textContent).toBe(
      'Rewriting Self-Custody Rules',
    );
  });

  it('이미지가 있으면 부제는 언제나 본문에 남는다', () => {
    const withImage = buildCard({
      quote: null,
      media: { image: 'https://example.com/a.jpg', href: null, cta: null },
    });
    expect(showsSubtitleInBody(withImage)).toBe(true);
  });

  it('이미지가 있는 카드는 그대로 이미지를 쓴다', () => {
    const card = buildCard({
      media: { image: 'https://example.com/a.jpg', href: null, cta: null },
    });
    const { container } = render(<CardArt card={card} date={DATE} media={{}} shouldLoad />);

    expect(container.querySelector('.art-type')).toBeNull();
    expect(container.querySelector('img')?.getAttribute('src')).toContain('/api/img/2026-08-05/4');
  });
});
