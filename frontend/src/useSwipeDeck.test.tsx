import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { useSwipeDeck } from './useSwipeDeck';

function Deck({ total }: { total: number }) {
  const { current, trackRef, prev, next } = useSwipeDeck(total);
  return (
    <div>
      <span data-testid="current">{current}</span>
      <button onClick={prev}>prev</button>
      <button onClick={next}>next</button>
      <div className="track" ref={trackRef}>
        {Array.from({ length: total }, (_, i) => (
          <div className="slide" key={i} />
        ))}
      </div>
    </div>
  );
}

const current = () => screen.getByTestId('current').textContent;

describe('useSwipeDeck', () => {
  it('advances on ArrowRight and retreats on ArrowLeft', () => {
    render(<Deck total={3} />);
    expect(current()).toBe('0');

    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(current()).toBe('1');

    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(current()).toBe('0');
  });

  it('clamps at both ends', () => {
    render(<Deck total={2} />);

    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(current()).toBe('0');

    fireEvent.keyDown(window, { key: 'ArrowRight' });
    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(current()).toBe('1');
  });
});
