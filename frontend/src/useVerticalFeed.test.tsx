import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { useVerticalFeed } from './useVerticalFeed';

function Feed({ total, locked = false }: { total: number; locked?: boolean }) {
  const { current, trackRef, prev, next } = useVerticalFeed(total, locked);
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

describe('useVerticalFeed', () => {
  it('advances on ArrowDown and retreats on ArrowUp', () => {
    render(<Feed total={3} />);
    expect(current()).toBe('0');

    fireEvent.keyDown(window, { key: 'ArrowDown' });
    expect(current()).toBe('1');

    fireEvent.keyDown(window, { key: 'ArrowUp' });
    expect(current()).toBe('0');
  });

  it('advances on PageDown and Space', () => {
    render(<Feed total={4} />);

    fireEvent.keyDown(window, { key: 'PageDown' });
    expect(current()).toBe('1');

    fireEvent.keyDown(window, { key: ' ' });
    expect(current()).toBe('2');
  });

  it('clamps at both ends', () => {
    render(<Feed total={2} />);

    fireEvent.keyDown(window, { key: 'ArrowUp' });
    expect(current()).toBe('0');

    fireEvent.keyDown(window, { key: 'ArrowDown' });
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    expect(current()).toBe('1');
  });

  it('ignores keyboard navigation while locked', () => {
    render(<Feed total={3} locked />);

    fireEvent.keyDown(window, { key: 'ArrowDown' });

    expect(current()).toBe('0');
  });

  it('leaves Space alone when a control has focus', () => {
    render(<Feed total={3} />);

    fireEvent.keyDown(screen.getByText('next'), { key: ' ' });

    expect(current()).toBe('0');
  });

  it('keeps horizontal arrows free for other handlers', () => {
    render(<Feed total={3} />);

    fireEvent.keyDown(window, { key: 'ArrowRight' });

    expect(current()).toBe('0');
  });
});
