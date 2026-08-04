import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { TrendingSheet } from './TrendingSheet';
import type { TrendingItem } from './content';

function buildItem(overrides: Partial<TrendingItem> = {}): TrendingItem {
  return {
    rank: 1,
    topic: '콜드카드 지갑 취약점',
    heat: 100,
    mentions: 30,
    sources: 13,
    links: [
      { label: '토큰포스트 원문', href: 'https://a.example/1' },
      { label: 'CoinDesk 원문', href: 'https://b.example/2' },
    ],
    ...overrides,
  };
}

describe('TrendingSheet', () => {
  it('renders nothing while closed', () => {
    const { container } = render(<TrendingSheet item={null} onClose={() => {}} />);

    expect(container.querySelector('.sheet')).toBeNull();
  });

  it('lists every source link for the topic', () => {
    const { container } = render(<TrendingSheet item={buildItem()} onClose={() => {}} />);

    const links = container.querySelectorAll('.trending-sheet-links a');
    expect(links).toHaveLength(2);
    expect(links[0].getAttribute('href')).toBe('https://a.example/1');
    expect(links[0].textContent).toContain('토큰포스트 원문');
  });

  it('opens each link in a new tab without leaking the opener', () => {
    const { container } = render(<TrendingSheet item={buildItem()} onClose={() => {}} />);

    for (const link of container.querySelectorAll('.trending-sheet-links a')) {
      expect(link.getAttribute('target')).toBe('_blank');
      // noopener 없이 새 탭을 열면 열린 페이지가 window.opener로 이쪽을 조작할 수 있다.
      expect(link.getAttribute('rel')).toContain('noopener');
    }
  });

  it('says so instead of showing an empty list when the topic has no links', () => {
    const { container } = render(
      <TrendingSheet item={buildItem({ links: null })} onClose={() => {}} />,
    );

    expect(container.querySelector('.trending-sheet-links')).toBeNull();
    expect(container.textContent).toContain('원문 목록이 없습니다');
  });

  it('closes on the close button, the backdrop, and Escape', () => {
    const onClose = vi.fn();
    const { container } = render(<TrendingSheet item={buildItem()} onClose={onClose} />);

    fireEvent.click(container.querySelector('.sheet-close') as HTMLElement);
    fireEvent.click(container.querySelector('.sheet-backdrop') as HTMLElement);
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it('keeps clicks inside the sheet from closing it', () => {
    const onClose = vi.fn();
    const { container } = render(<TrendingSheet item={buildItem()} onClose={onClose} />);

    fireEvent.click(container.querySelector('.sheet-scroll') as HTMLElement);

    expect(onClose).not.toHaveBeenCalled();
  });
});
