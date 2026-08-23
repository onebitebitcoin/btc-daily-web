import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useVerticalFeed } from './useVerticalFeed';

/** jsdom 에는 IntersectionObserver 도 스크롤도 없다. 그래서 관찰자 콜백을 손으로
 *  때리고 scrollIntoView 를 기록하는 가짜를 심는다 — 이 경로를 안 밟으면 아래 두
 *  회귀(되돌림·두 칸 점프)를 테스트가 통째로 지나쳐 버린다. */
type IOEntry = { target: Element; isIntersecting: boolean; intersectionRatio: number };
let observed: Element[] = [];
let fireIO: (entries: IOEntry[]) => void = () => {};
let scrolledTo: number[] = [];

class FakeIntersectionObserver {
  constructor(cb: (entries: IOEntry[]) => void) {
    fireIO = cb;
  }
  observe(el: Element) {
    observed.push(el);
  }
  disconnect() {
    observed = [];
  }
}

beforeEach(() => {
  observed = [];
  scrolledTo = [];
  vi.useFakeTimers();
  (globalThis as { IntersectionObserver?: unknown }).IntersectionObserver = FakeIntersectionObserver;
  Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
    scrolledTo.push(observed.indexOf(this));
  });
});

afterEach(() => {
  vi.useRealTimers();
  delete (globalThis as { IntersectionObserver?: unknown }).IntersectionObserver;
});

/** 스냅 애니메이션이 끝날 때까지 기다린다(가짜 타이머). */
function settle() {
  act(() => {
    vi.advanceTimersByTime(1000);
  });
}

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

    // 이동이 정착하기 전 입력은 무시된다 — 안 그러면 한 번에 두 칸씩 건너뛴다.
    settle();
    fireEvent.keyDown(window, { key: 'ArrowUp' });
    expect(current()).toBe('0');
  });

  it('advances on PageDown and Space', () => {
    render(<Feed total={4} />);

    fireEvent.keyDown(window, { key: 'PageDown' });
    expect(current()).toBe('1');

    settle();
    fireEvent.keyDown(window, { key: ' ' });
    expect(current()).toBe('2');
  });

  it('clamps at both ends', () => {
    render(<Feed total={2} />);

    fireEvent.keyDown(window, { key: 'ArrowUp' });
    expect(current()).toBe('0');

    settle();
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    settle();
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

  it('떠나는 슬라이드가 콜백 뒤쪽에 실려도 current 가 되돌아가지 않는다', () => {
    // 실제 사고: threshold 0.6 을 지나는 순간 떠나는 슬라이드도 isIntersecting 이라
    // 콜백에 같이 실린다. 배치 안 엔트리 순서는 보장되지 않아서, 마지막에 쓰는 방식이면
    // current 가 이전 값으로 되돌아간다 → 다음 클릭이 제자리 goTo 가 되어 안 넘어간다.
    render(<Feed total={5} />);
    fireEvent.click(screen.getByText('next'));
    expect(current()).toBe('1');

    act(() => {
      fireIO([
        { target: observed[1], isIntersecting: true, intersectionRatio: 0.62 },
        { target: observed[0], isIntersecting: true, intersectionRatio: 0.61 },
      ]);
    });

    expect(current()).toBe('1');
  });

  it('되돌림 뒤에도 다음 클릭이 제자리에 머물지 않는다', () => {
    render(<Feed total={5} />);
    fireEvent.click(screen.getByText('next'));
    act(() => {
      fireIO([
        { target: observed[1], isIntersecting: true, intersectionRatio: 0.62 },
        { target: observed[0], isIntersecting: true, intersectionRatio: 0.61 },
      ]);
    });
    settle();

    fireEvent.click(screen.getByText('next'));

    expect(scrolledTo[scrolledTo.length - 1]).toBe(2);
  });

  it('애니메이션이 끝나기 전에 또 눌러도 한 칸만 간다', () => {
    // 스무스 스크롤이 진행 중이면 화면은 아직 출발점 근처다. 낙관적 current 로 다음
    // 목표를 계산하면 두 번째 클릭이 0에서 2로 건너뛴다.
    render(<Feed total={5} />);
    const next = screen.getByText('next');

    fireEvent.click(next);
    fireEvent.click(next);

    expect(scrolledTo).toEqual([1]);
  });

  it('정착한 뒤에는 다시 눌러 이동할 수 있다', () => {
    render(<Feed total={5} />);
    const next = screen.getByText('next');

    fireEvent.click(next);
    settle();
    fireEvent.click(next);

    expect(scrolledTo).toEqual([1, 2]);
  });

  it('관찰자가 목표 도착을 알리면 곧바로 다음 이동을 받는다', () => {
    render(<Feed total={5} />);
    const next = screen.getByText('next');

    fireEvent.click(next);
    act(() => {
      fireIO([{ target: observed[1], isIntersecting: true, intersectionRatio: 0.95 }]);
    });
    fireEvent.click(next);

    expect(scrolledTo).toEqual([1, 2]);
  });

  it('스와이프로 옮겨간 위치를 관찰자가 반영한다', () => {
    render(<Feed total={5} />);

    act(() => {
      fireIO([{ target: observed[2], isIntersecting: true, intersectionRatio: 0.9 }]);
    });

    expect(current()).toBe('2');
  });

  it('이동 중 스와이프로 가로챈 위치를 따라간다', () => {
    // 실제 브라우저에서 발견: 버튼을 누른 직후 사용자가 스와이프로 다른 슬라이드로
    // 가면, 목표가 아닌 보고를 전부 버리는 구현은 그 위치를 영영 못 따라잡는다.
    // 그 뒤 버튼을 누르면 낡은 인덱스 기준이라 화면이 뒤로 점프한다.
    render(<Feed total={10} />);
    fireEvent.click(screen.getByText('next')); // 0 → 1 이동 시작

    act(() => {
      fireIO([{ target: observed[7], isIntersecting: true, intersectionRatio: 0.9 }]);
    });

    expect(current()).toBe('7');
    fireEvent.click(screen.getByText('next'));
    expect(scrolledTo[scrolledTo.length - 1]).toBe(8);
  });
});