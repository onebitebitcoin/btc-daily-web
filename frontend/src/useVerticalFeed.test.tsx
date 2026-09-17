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
  delete (window as { onscrollend?: unknown }).onscrollend;
});

/** `'onscrollend' in window` 를 통과시켜 지원 브라우저 경로를 밟게 한다.
 *  jsdom 은 이 이벤트를 구현하지 않아서 심지 않으면 타이머 경로만 돈다. */
function enableScrollEnd() {
  (window as { onscrollend?: unknown }).onscrollend = null;
}

/** 스냅 애니메이션이 끝날 때까지 기다린다(가짜 타이머). */
function settle() {
  act(() => {
    vi.advanceTimersByTime(1000);
  });
}

function Feed({ total, locked = false }: { total: number; locked?: boolean }) {
  const { current, moving, trackRef, prev, next } = useVerticalFeed(total, locked);
  return (
    <div>
      <span data-testid="current">{current}</span>
      <span data-testid="moving">{moving ? 'yes' : 'no'}</span>
      <button onClick={prev}>prev</button>
      <button onClick={next}>next</button>
      {/* ShortsFeed 와 똑같이, 실을 내용이 없으면 트랙 자체를 그리지 않는다.
          트랙이 나중에 생기는 이 순서를 재현해야 리스너 등록 회귀를 잡는다. */}
      {total > 0 && (
        <div className="track" data-testid="track" ref={trackRef}>
          {Array.from({ length: total }, (_, i) => (
            <div className="slide" key={i} />
          ))}
        </div>
      )}
    </div>
  );
}

const current = () => screen.getByTestId('current').textContent;
const moving = () => screen.getByTestId('moving').textContent;

describe('useVerticalFeed', () => {
  it('advances on ArrowDown and retreats on ArrowUp', () => {
    render(<Feed total={3} />);
    expect(current()).toBe('0');

    fireEvent.keyDown(window, { key: 'ArrowDown' });
    expect(current()).toBe('1');

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

  it('이동이 끝나기 전에 또 눌러도 한 칸만 간다', () => {
    // 화면에서는 버튼이 그동안 비활성이라 눌리지 않는다(FeedNav). 키보드와 진행바
    // 탭은 버튼을 거치지 않으므로 훅 안에서도 막는다.
    render(<Feed total={5} />);
    const next = screen.getByText('next');

    fireEvent.click(next);
    fireEvent.click(next);

    expect(scrolledTo).toEqual([1]);
    expect(current()).toBe('1');
  });

  it('이동 중에는 moving 이 켜지고 정착하면 꺼진다', () => {
    // 이 값이 위/아래 버튼의 비활성 상태를 만든다.
    render(<Feed total={5} />);
    expect(moving()).toBe('no');

    fireEvent.click(screen.getByText('next'));
    expect(moving()).toBe('yes');

    settle();
    expect(moving()).toBe('no');
  });

  it('정착한 뒤에는 다시 눌러 이동할 수 있다', () => {
    render(<Feed total={5} />);
    const next = screen.getByText('next');

    fireEvent.click(next);
    settle();
    fireEvent.click(next);

    expect(scrolledTo).toEqual([1, 2]);
  });

  it('관찰자 보고만으로는 잠금이 풀리지 않는다', () => {
    // 관찰자는 임계값(60%)을 지나는 순간 보고하는데 그때 화면은 아직 움직이는 중이다.
    // 거기서 버튼이 살아나면 애니메이션이 끝나기 전에 다음 이동이 겹쳐 시작된다.
    render(<Feed total={5} />);
    const next = screen.getByText('next');

    fireEvent.click(next);
    act(() => {
      fireIO([{ target: observed[1], isIntersecting: true, intersectionRatio: 0.95 }]);
    });
    fireEvent.click(next);

    expect(scrolledTo).toEqual([1]);
    expect(moving()).toBe('yes');
  });

  it('스크롤이 멎으면 곧바로 다음 이동을 받는다', () => {
    enableScrollEnd();
    const { rerender } = render(<Feed total={0} />);
    rerender(<Feed total={5} />);
    const track = screen.getByTestId('track');
    const next = screen.getByText('next');

    fireEvent.click(next);
    act(() => {
      track.dispatchEvent(new Event('scrollend'));
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

  it('구간 밖으로 멀리 뛴 위치는 관찰자 보고를 받아 따라간다', () => {
    // 딥링크나 캘린더 이동으로 화면이 멀리 뛰는 경우다. 목표가 아닌 보고를 전부
    // 버리는 구현은 그 위치를 영영 못 따라잡고, 다음 이동이 낡은 인덱스 기준이라
    // 화면이 뒤로 점프한다.
    render(<Feed total={10} />);
    fireEvent.click(screen.getByText('next')); // 0 → 1 이동 시작

    act(() => {
      fireIO([{ target: observed[7], isIntersecting: true, intersectionRatio: 0.9 }]);
    });

    expect(current()).toBe('7');
    settle();
    fireEvent.click(screen.getByText('next'));
    expect(scrolledTo[scrolledTo.length - 1]).toBe(8);
  });

  it('트랙이 나중에 생겨도 scrollend 가 이동 잠금을 푼다', () => {
    // 실제 앱의 결함: ShortsFeed 는 데이터가 오기 전까지 트랙 대신 로딩 화면을
    // 그린다. 리스너 등록 effect 가 trackRef 만 보고 한 번만 돌면, 그 한 번이
    // 트랙 없는 시점이라 scrollend 리스너가 영영 안 붙는다. 그러면 잠금이 관찰자
    // 보고나 700ms 타이머를 기다려야만 풀려서 그사이 입력이 계속 씹힌다.
    enableScrollEnd();
    const { rerender } = render(<Feed total={0} />);
    rerender(<Feed total={5} />);
    const track = screen.getByTestId('track');

    fireEvent.click(screen.getByText('next')); // 0 → 1 이동 시작(잠금 걸림)
    act(() => {
      track.dispatchEvent(new Event('scrollend'));
    });

    // 잠금이 풀렸으면 출발 슬라이드 보고도 그대로 받는다. 안 풀렸으면 그 보고는
    // "떠나온 슬라이드"로 취급되어 버려지고 current 가 1에 머문다.
    act(() => {
      fireIO([{ target: observed[0], isIntersecting: true, intersectionRatio: 0.9 }]);
    });

    expect(current()).toBe('0');
  });

});