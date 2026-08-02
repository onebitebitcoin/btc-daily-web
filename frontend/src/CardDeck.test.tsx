import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { CardDeck, type EditionContent } from './CardDeck';
import fixture from './fixtures/content.json';

const content = fixture as EditionContent;
const media = { 'fed-macro': '/fed-macro.jpg' };

const renderDeck = () => render(<CardDeck content={content} media={media} />);

describe('CardDeck', () => {
  it('renders cover, every card and closing as one flat slide sequence', () => {
    const { container } = renderDeck();
    expect(container.querySelectorAll('.slide')).toHaveLength(content.cards.length + 2);
    expect(screen.getByText(content.cover.eyebrow)).toBeDefined();
    expect(screen.getByText(content.closing.stamp)).toBeDefined();
  });

  it('numbers cards against the card count, and the counter against the total', () => {
    const { container } = renderDeck();
    expect(container.querySelector('.counter')?.textContent).toBe(
      `01 / ${content.cards.length + 2}`,
    );
    expect(container.querySelector('.card-num')?.textContent).toBe(`01 / ${content.cards.length}`);
  });

  it('falls back to a numbered placeholder when the image is missing', () => {
    const { container } = renderDeck();
    const arts = container.querySelectorAll('.art');
    expect(container.querySelector('.art img')?.getAttribute('src')).toBe('/fed-macro.jpg');
    // the cover mirrors card 1's art, so /fed-macro.jpg resolves twice (cover + card 1);
    // every other card with a media block but no matching file renders .art-blank
    expect(container.querySelectorAll('.art-blank').length).toBe(arts.length - 2);
  });

  it('marks the chip emphasis with the reference class names', () => {
    const { container } = renderDeck();
    expect(container.querySelector('.badge.emph-a')).not.toBeNull();
    expect(container.querySelector('.badge.emph-b')).not.toBeNull();
  });

  it('disables prev on the cover and advances the active slide with the next button', () => {
    const { container } = renderDeck();
    const prev = container.querySelector<HTMLButtonElement>('.nav-btn.prev')!;
    const next = container.querySelector<HTMLButtonElement>('.nav-btn.next')!;

    expect(prev.disabled).toBe(true);
    fireEvent.click(next);

    expect(prev.disabled).toBe(false);
    expect(container.querySelector('.counter')?.textContent).toBe(
      `02 / ${content.cards.length + 2}`,
    );
    const slides = container.querySelectorAll('.slide');
    expect(slides[1].className).toContain('is-active');
  });

  it('sends the deck back to the cover from the closing restart button', () => {
    const { container } = renderDeck();
    fireEvent.click(container.querySelector('.nav-btn.next')!);
    expect(container.querySelector('.counter')?.textContent).not.toBe(
      `01 / ${content.cards.length + 2}`,
    );

    fireEvent.click(screen.getByText(content.closing.restart));
    expect(container.querySelector('.counter')?.textContent).toBe(
      `01 / ${content.cards.length + 2}`,
    );
  });

  it('renders no .qa-block for cards without qa (pre-existing published editions)', () => {
    const { container } = renderDeck();
    expect(container.querySelector('.qa-block')).toBeNull();
  });

  it('renders exactly 3 .qa-item for a card with qa, and toggles a details on summary click', () => {
    const qaCard = {
      ...content.cards[0],
      qa: [
        { question: 'Q1?', answer: 'A1', sources: ['https://example.com/1'] },
        { question: 'Q2?', answer: 'A2', sources: [] },
        { question: 'Q3?', answer: 'A3', sources: ['https://example.com/3'] },
      ],
    };
    const qaContent: EditionContent = {
      ...content,
      cards: [qaCard, ...content.cards.slice(1)],
    };
    const { container } = render(<CardDeck content={qaContent} media={media} />);

    const items = container.querySelectorAll('.qa-item');
    expect(items).toHaveLength(3);

    const firstDetails = items[0] as HTMLDetailsElement;
    expect(firstDetails.open).toBe(false);

    const summary = firstDetails.querySelector('summary')!;
    fireEvent.click(summary);

    expect(firstDetails.open).toBe(true);
  });
});
