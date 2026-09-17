import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { CardSlide } from './slides/CardSlide';
import type { Card } from './content';

const DATE = '2026-09-18';

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

function renderSlide(props: Partial<Parameters<typeof CardSlide>[0]> = {}) {
  const onToggleLike = vi.fn();
  const onShare = vi.fn();
  render(
    <CardSlide
      card={buildCard()}
      date={DATE}
      total={10}
      media={{}}
      isActive
      shouldLoadImage
      onOpenDetail={() => {}}
      likeCount={0}
      liked={false}
      onToggleLike={onToggleLike}
      onShare={onShare}
      {...props}
    />,
  );
  return { onToggleLike, onShare };
}

describe('카드의 좋아요·공유 버튼', () => {
  it('아무도 안 누른 카드는 숫자를 감춘다', () => {
    renderSlide({ likeCount: 0 });

    expect(screen.getByLabelText('좋아요').textContent).toBe('');
  });

  it('쌓인 수가 있으면 숫자를 보여준다', () => {
    renderSlide({ likeCount: 12 });

    expect(screen.getByLabelText('좋아요').textContent).toBe('12');
  });

  it('누른 상태는 이름과 상태 속성으로도 드러난다', () => {
    // 색과 채워진 하트만으로 구분하면 색 구분이 어려운 사람이 알 수 없다.
    renderSlide({ liked: true, likeCount: 3 });

    const button = screen.getByLabelText('좋아요 취소');
    expect(button.getAttribute('aria-pressed')).toBe('true');
    expect(button.className).toContain('is-on');
  });

  it('좋아요를 누르면 핸들러가 불린다', () => {
    const { onToggleLike } = renderSlide();

    fireEvent.click(screen.getByLabelText('좋아요'));

    expect(onToggleLike).toHaveBeenCalledTimes(1);
  });

  it('공유를 누르면 핸들러가 불린다', () => {
    const { onShare } = renderSlide();

    fireEvent.click(screen.getByLabelText('이 카드 링크 공유'));

    expect(onShare).toHaveBeenCalledTimes(1);
  });
});
