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
      { title: '콜드카드 지갑의 키 생성 취약점, 1억 달러 피해', href: 'https://a.example/1', source: '토큰포스트' },
      { title: 'Ledger Says Coldcard Exploit Shows Wallet Risk', href: 'https://b.example/2', source: 'CoinDesk' },
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
  });

  it('shows the article headline, not just the outlet name', () => {
    const { container } = render(<TrendingSheet item={buildItem()} onClose={() => {}} />);

    const titles = container.querySelectorAll('.trending-link-title');
    expect(titles[0].textContent).toBe('콜드카드 지갑의 키 생성 취약점, 1억 달러 피해');
    expect(titles[1].textContent).toBe('Ledger Says Coldcard Exploit Shows Wallet Risk');
  });

  it('credits the outlet alongside the headline', () => {
    const { container } = render(<TrendingSheet item={buildItem()} onClose={() => {}} />);

    const sources = container.querySelectorAll('.trending-link-source');
    expect([...sources].map((s) => s.textContent)).toEqual(['토큰포스트', 'CoinDesk']);
  });

  it('omits the outlet line when the article has no source', () => {
    const item = buildItem({
      links: [{ title: '출처 없는 기사', href: 'https://a.example/1' }],
    });

    const { container } = render(<TrendingSheet item={item} onClose={() => {}} />);

    expect(container.querySelector('.trending-link-title')?.textContent).toBe('출처 없는 기사');
    expect(container.querySelector('.trending-link-source')).toBeNull();
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
