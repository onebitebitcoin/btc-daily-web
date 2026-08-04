import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { DetailSheet } from './DetailSheet';
import { hasMoreToRead, type Card } from './content';

const card: Card = {
  num: 3,
  chip: { text: '거시', emphasis: 'primary' },
  title: '연준이 금리를 동결했다',
  subtitle: '9월 인하 기대는 후퇴',
  chips_label: '관련',
  chips: ['연준', '금리'],
  body: '본문 전문이 여기에 들어간다.',
  quote: '시장은 아직 인하를 믿는다',
  link: { label: '원문 보기', href: 'https://example.com/a' },
  media: null,
  qa: [{ question: '왜 중요한가?', answer: '유동성 때문이다.', sources: ['https://example.com/s'] }],
};

const plainCard: Card = {
  ...card,
  body: '짧은 본문.',
  quote: null,
  qa: null,
};

describe('hasMoreToRead', () => {
  it('is true when the card carries a quote or Q&A', () => {
    expect(hasMoreToRead(card)).toBe(true);
  });

  it('is false for a short card with nothing extra', () => {
    expect(hasMoreToRead(plainCard)).toBe(false);
  });

  it('is true when the body alone would be clamped', () => {
    expect(hasMoreToRead({ ...plainCard, body: '가'.repeat(200) })).toBe(true);
  });
});

describe('DetailSheet', () => {
  it('renders nothing when closed', () => {
    const { container } = render(<DetailSheet card={null} onClose={() => {}} />);

    expect(container.querySelector('.sheet')).toBeNull();
  });

  it('shows the full body, quote, link and Q&A', () => {
    render(<DetailSheet card={card} onClose={() => {}} />);

    expect(screen.getByText(card.body)).toBeDefined();
    expect(screen.getByText('“시장은 아직 인하를 믿는다”')).toBeDefined();
    expect(screen.getByText('원문 보기')).toBeDefined();
    expect(screen.getByText('왜 중요한가?')).toBeDefined();
  });

  it('closes on the close button', () => {
    const onClose = vi.fn();
    render(<DetailSheet card={card} onClose={onClose} />);

    fireEvent.click(screen.getByText('닫기'));

    expect(onClose).toHaveBeenCalled();
  });

  it('closes on backdrop click but not on sheet click', () => {
    const onClose = vi.fn();
    const { container } = render(<DetailSheet card={card} onClose={onClose} />);

    fireEvent.click(container.querySelector('.sheet') as Element);
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(container.querySelector('.sheet-backdrop') as Element);
    expect(onClose).toHaveBeenCalled();
  });

  it('closes on Escape', () => {
    const onClose = vi.fn();
    render(<DetailSheet card={card} onClose={onClose} />);

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(onClose).toHaveBeenCalled();
  });

  it('is announced as a modal dialog labelled by the card title', () => {
    render(<DetailSheet card={card} onClose={() => {}} />);

    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.getAttribute('aria-label')).toBe(card.title);
  });
});
