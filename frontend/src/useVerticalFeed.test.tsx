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
  const { current, trackRef, prev, next } = useVerticalFeed(total, locked);
  return (
    <div>
      <span data-testid="current">{current}</span>
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

  it('애니메이션이 끝나기 전에 또 눌러도 누른 횟수만큼 간다', () => {
    // 이동이 끝나기 전 입력을 버리던 시절의 제보: 버튼을 연속으로 두 번 누르면 두
    // 번째가 씹혀서 "멈춘다"고 느낀다. 진행 중인 목표를 기준으로 이어 붙인다.
    render(<Feed total={5} />);
    const next = screen.getByText('next');

    fireEvent.click(next);
    fireEvent.click(next);

    expect(scrolledTo).toEqual([1, 2]);
    expect(current()).toBe('2');
  });

  it('연타로 건너뛰는 중간 슬라이드 보고에는 흔들리지 않는다', () => {
    // 0 → 2 로 가는 도중 1번 슬라이드가 threshold 를 지나며 보고된다. 그걸 받으면
    // 진행바가 1로 물러났다가 2로 올라가는 깜빡임이 보인다.
    render(<Feed total={5} />);
    const next = screen.getByText('next');

    fireEvent.click(next);
    fireEvent.click(next);
    act(() => {
      fireIO([{ target: observed[1], isIntersecting: true, intersectionRatio: 0.9 }]);
    });

    expect(current()).toBe('2');
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

  describe('스냅이 도는 동안 새 스와이프를 막는다', () => {
    /** 네이티브 스냅은 애니메이션 중에 손가락이 닿으면 그 자리에서 멈추고 손가락을
     *  따라간다. 그러면 카드가 두 장 사이에 걸치거나 엉뚱한 카드로 넘어간다.
     *  잠금은 `is-settling` 클래스로 걸고, CSS 가 touch-action: none 을 준다. */
    const settling = () => screen.getByTestId('track').classList.contains('is-settling');

    it('손을 뗀 순간부터 잠근다', () => {
      render(<Feed total={5} />);
      const track = screen.getByTestId('track');
      expect(settling()).toBe(false);

      fireEvent.touchEnd(track);

      expect(settling()).toBe(true);
    });

    it('스크롤이 멎으면 곧바로 푼다', () => {
      // 상한(600ms)을 기다리지 않는다. 스냅은 대개 그보다 훨씬 빨리 끝난다.
      render(<Feed total={5} />);
      const track = screen.getByTestId('track');
      fireEvent.touchEnd(track);

      act(() => {
        track.dispatchEvent(new Event('scrollend'));
      });

      expect(settling()).toBe(false);
    });

    it('scrollend 가 오지 않아도 상한이 지나면 푼다', () => {
      // 미지원 브라우저와, 끝 슬라이드에서 더 밀어 스크롤 자체가 없는 경우를 위한
      // 안전장치다. 없으면 잠금이 안 풀려 스와이프가 통째로 죽는다.
      render(<Feed total={5} />);
      const track = screen.getByTestId('track');
      fireEvent.touchEnd(track);

      settle();

      expect(settling()).toBe(false);
    });

    it('연달아 스와이프하면 잠금 시계를 다시 잡는다', () => {
      render(<Feed total={5} />);
      const track = screen.getByTestId('track');

      fireEvent.touchEnd(track);
      act(() => {
        vi.advanceTimersByTime(500);
      });
      fireEvent.touchEnd(track);
      act(() => {
        vi.advanceTimersByTime(300); // 첫 번째 기준이면 이미 풀렸을 시점
      });

      expect(settling()).toBe(true);
    });

    it('터치가 취소돼도 잠금이 남지 않는다', () => {
      // 전화가 오거나 시스템 제스처가 가로채면 touchend 대신 touchcancel 이 온다.
      render(<Feed total={5} />);
      const track = screen.getByTestId('track');

      fireEvent.touchCancel(track);
      expect(settling()).toBe(true);

      settle();
      expect(settling()).toBe(false);
    });

    it('버튼 이동은 잠그지 않는다', () => {
      // 손가락이 닿지 않은 이동이라 스냅이 가로채일 일이 없다. 여기까지 잠그면
      // 버튼을 잘못 눌렀을 때 스와이프로 바로 고칠 수 없어진다.
      render(<Feed total={5} />);

      fireEvent.click(screen.getByText('next'));

      expect(settling()).toBe(false);
    });
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