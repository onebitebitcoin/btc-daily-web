import { useCallback, useEffect, useRef, useState } from 'react';

/** 프로그램이 시작한 스크롤이 끝났다고 보기까지 기다리는 최대 시간(ms).
 *
 *  정상 경로에서는 관찰자가 목표 도착을 알려주거나 `scrollend` 가 와서 그 전에 풀린다.
 *  이 타이머는 그 둘이 안 오는 경우(이미 목표에 서 있어 스크롤 자체가 없거나,
 *  scrollend 미지원 브라우저에서 관찰자 임계값을 안 건드릴 만큼 짧게 움직인 경우)를
 *  위한 안전장치다 — 없으면 잠금이 안 풀려 피드가 통째로 멈춘다.
 */
const SETTLE_TIMEOUT_MS = 700;

/** 스와이프로 시작된 스냅이 도는 동안 새 터치를 받지 않는 시간의 상한(ms).
 *
 *  `scrollend` 를 지원하는 브라우저에서는 스크롤이 멎는 즉시 풀리므로 이 값까지
 *  가지 않는다. 미지원 브라우저와, 스크롤이 아예 일어나지 않아 `scrollend` 가 오지
 *  않는 경우(끝 슬라이드에서 더 밀었을 때)를 위한 안전장치다 — 없으면 잠금이 안 풀려
 *  스와이프가 통째로 죽는다.
 */
const GESTURE_LOCK_MAX_MS = 600;

/** 세로 스냅 피드의 현재 인덱스를 추적하고 이동시킨다.
 *
 *  슬라이드가 뒤로 계속 붙는(무한 피드) 구조라 `total`이 바뀔 때마다 관찰 대상을
 *  다시 등록한다. 시트가 열려 있는 동안에는 키보드 이동을 막아야 시트 안에서
 *  방향키를 누를 때 뒤 피드가 같이 움직이지 않는다.
 *
 *  ## 이동 중 상태 추적이 필요한 이유
 *
 *  `current` 를 쓰는 주체가 둘이다 — 이동 요청(버튼·키보드)이 낙관적으로 쓰고,
 *  IntersectionObserver 도 쓴다. 스무스 스크롤이 도는 동안 둘이 겹치면 2026-08-23
 *  버튼 도입 뒤 제보된 증상이 그대로 난다. threshold 0.6 을 지나는 순간에는 *떠나는*
 *  슬라이드도 `isIntersecting` 이라 콜백에 같이 실리고, 한 배치 안 엔트리 순서는
 *  명세상 보장이 없다. 마지막 엔트리를 그대로 쓰면 `current` 가 이전 값으로
 *  되돌아가고, 그러면 다음 클릭이 지금 화면과 같은 인덱스로 가는 제자리 이동이
 *  되어 아무 일도 일어나지 않는다.
 *
 *  그래서 이동을 시작하면 출발·목표를 `pendingRef` 에 적고, 정착할 때까지 출발점과
 *  목표 *사이를* 지나가는 보고를 버린다. 구간 밖 보고는 받아야 한다 — 사용자가 버튼을
 *  누른 직후 스와이프로 다른 슬라이드에 가버렸을 때 그 위치를 따라가야 하기 때문이다
 *  (전부 버리던 시절 실측: 스크롤은 8번인데 활성은 5번에 머물고, 다음 버튼이 6번으로
 *  뒤로 뛰었다).
 *
 *  ## 연타는 누른 횟수만큼 간다
 *
 *  2026-08-24까지는 이동이 끝나기 전에 들어온 요청을 통째로 버렸다. 한 번 클릭에 두
 *  장이 넘어가는 걸 막으려던 장치인데, 일부러 두 번 누른 경우까지 같이 막혀서 "버튼을
 *  연속으로 누르면 멈춘다"는 제보로 돌아왔다(2026-09-18). 지금은 버리지 않고 이미
 *  진행 중인 목표(`pending.to`)를 기준으로 다음 목표를 계산한다. 낙관적 `current` 가
 *  아직 갱신되기 전이어도 두 칸 점프나 제자리 이동이 생기지 않는다.
 */
export function useVerticalFeed(total: number, locked = false) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [current, setCurrent] = useState(0);
  /** 이동 중이면 출발·목표 인덱스, 정착했으면 null. */
  const pendingRef = useRef<{ from: number; to: number } | null>(null);
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // goTo 안에서 출발점을 읽으려고 둔다. state 를 직접 읽으면 슬라이드가 바뀔 때마다
  // goTo 가 새로 만들어지고, 그걸 의존하는 키보드 리스너까지 매번 다시 붙는다.
  const currentRef = useRef(0);
  currentRef.current = current;

  const clearSettle = useCallback(() => {
    pendingRef.current = null;
    if (settleTimerRef.current !== null) {
      clearTimeout(settleTimerRef.current);
      settleTimerRef.current = null;
    }
  }, []);

  const goTo = useCallback(
    (index: number) => {
      const clamped = Math.max(0, Math.min(total - 1, index));
      setCurrent(clamped);
      const slide = trackRef.current?.children[clamped];
      if (!slide) return;

      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      // 이동 중에 또 눌렀으면 출발점은 처음 것을 유지한다. 그래야 아래 관찰자가
      // 0→2 이동에서 지나가는 1번 슬라이드를 "구간 안"으로 알아보고 버린다.
      const from = pendingRef.current?.from ?? currentRef.current;
      pendingRef.current = { from, to: clamped };
      if (settleTimerRef.current !== null) clearTimeout(settleTimerRef.current);
      settleTimerRef.current = setTimeout(clearSettle, reduceMotion ? 0 : SETTLE_TIMEOUT_MS);

      slide.scrollIntoView({
        behavior: reduceMotion ? 'auto' : 'smooth',
        block: 'start',
        inline: 'nearest',
      });
    },
    [total, clearSettle],
  );

  /** 한 칸 이동. 이동이 진행 중이면 그 목표를 기준으로 삼아 연타한 만큼 누적시킨다. */
  const step = useCallback(
    (delta: number) => {
      const base = pendingRef.current?.to ?? currentRef.current;
      goTo(base + delta);
    },
    [goTo],
  );

  const prev = useCallback(() => step(-1), [step]);
  const next = useCallback(() => step(1), [step]);

  useEffect(() => clearSettle, [clearSettle]);

  useEffect(() => {
    if (locked) return;
    const onKeyDown = (e: KeyboardEvent) => {
      // 링크·버튼에 포커스가 있을 때의 스페이스는 그쪽 동작이어야 한다.
      const target = e.target as HTMLElement | null;
      const onControl = target?.closest?.('a, button, details, summary, input, textarea');
      if (e.key === 'ArrowUp' || e.key === 'PageUp') {
        e.preventDefault();
        prev();
      } else if (e.key === 'ArrowDown' || e.key === 'PageDown') {
        e.preventDefault();
        next();
      } else if (e.key === ' ' && !onControl) {
        e.preventDefault();
        next();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [prev, next, locked]);

  // 스크롤이 실제로 멎으면 타임아웃을 기다리지 않고 바로 잠금을 푼다.
  // (Chrome 114+/Firefox 109+/Safari 17.4+. 미지원 브라우저는 위 타이머가 맡는다.)
  //
  // `total` 을 의존성에 넣는 게 핵심이다. ShortsFeed 는 데이터가 도착하기 전까지
  // 트랙 대신 로딩 화면을 그리므로 첫 실행 때 `trackRef.current` 가 null 이다.
  // `clearSettle` 만 의존하면 그 한 번으로 끝나서 리스너가 영영 안 붙었다.
  useEffect(() => {
    const track = trackRef.current;
    if (!track || !('onscrollend' in window)) return;
    const onScrollEnd = () => clearSettle();
    track.addEventListener('scrollend', onScrollEnd);
    return () => track.removeEventListener('scrollend', onScrollEnd);
  }, [total, clearSettle]);

  // 스냅이 도는 동안에는 새 스와이프를 받지 않는다.
  //
  // 브라우저 네이티브 스냅은 애니메이션 도중에 손가락이 닿으면 그 자리에서 멈추고
  // 손가락을 따라간다. 그러면 카드가 두 장 사이에 걸친 채로 서거나 의도하지 않은
  // 카드로 넘어가서, 화면이 한 번에 어디로 갈지 예측할 수 없다.
  //
  // `touch-action: none` 을 잠깐 걸어 **새로 시작하는** 터치 제스처만 막는다. 이미
  // 돌고 있는 스크롤은 터치 시작 시점에 이미 판정이 끝났으므로 그대로 완주한다.
  // 스크롤을 `overflow: hidden` 으로 막으면 진행 중인 애니메이션까지 잘리므로 쓰지 않는다.
  //
  // `total` 을 의존성에 넣는 이유는 아래 scrollend 와 같다 — 트랙이 나중에 생긴다.
  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;

    let unlockTimer: ReturnType<typeof setTimeout> | null = null;

    const unlock = () => {
      track.classList.remove('is-settling');
      if (unlockTimer !== null) {
        clearTimeout(unlockTimer);
        unlockTimer = null;
      }
    };

    const onTouchEnd = () => {
      // 손을 뗀 순간부터 관성과 스냅이 돈다. 여기서부터 잠근다.
      track.classList.add('is-settling');
      if (unlockTimer !== null) clearTimeout(unlockTimer);
      unlockTimer = setTimeout(unlock, GESTURE_LOCK_MAX_MS);
    };

    track.addEventListener('touchend', onTouchEnd, { passive: true });
    track.addEventListener('touchcancel', onTouchEnd, { passive: true });
    track.addEventListener('scrollend', unlock);
    return () => {
      unlock();
      track.removeEventListener('touchend', onTouchEnd);
      track.removeEventListener('touchcancel', onTouchEnd);
      track.removeEventListener('scrollend', unlock);
    };
  }, [total]);

  useEffect(() => {
    const track = trackRef.current;
    if (!track || typeof IntersectionObserver === 'undefined') return;
    const slides = Array.from(track.children);
    const io = new IntersectionObserver(
      (entries) => {
        // 배치에서 가장 많이 보이는 슬라이드 하나만 고른다. 엔트리 순서에 기대면
        // 떠나는 슬라이드가 뒤에 실린 배치에서 current 가 되돌아간다.
        let best: IntersectionObserverEntry | null = null;
        for (const entry of entries) {
          if (!entry.isIntersecting || entry.intersectionRatio <= 0.6) continue;
          if (!best || entry.intersectionRatio > best.intersectionRatio) best = entry;
        }
        if (!best) return;

        const index = slides.indexOf(best.target);
        // 슬라이드가 붙는 중이라 아직 이 배열에 없는 노드면 판단을 미룬다.
        if (index < 0) return;

        const pending = pendingRef.current;
        // 출발점과 목표 사이를 지나가는 중간 보고만 버린다. 목표에 도착했거나 그
        // 구간 밖이면 받는다 — 구간 밖은 사용자가 이동 중에 스와이프로 가로챈
        // 위치이고, 그것마저 버리면 영영 못 따라잡아 다음 버튼이 뒤로 점프한다.
        if (pending !== null && index !== pending.to) {
          const lo = Math.min(pending.from, pending.to);
          const hi = Math.max(pending.from, pending.to);
          if (index >= lo && index <= hi) return;
        }
        clearSettle();
        setCurrent(index);
      },
      { root: track, threshold: [0.6] },
    );
    slides.forEach((s) => io.observe(s));
    return () => io.disconnect();
  }, [total, clearSettle]);

  return { current, trackRef, goTo, prev, next };
}
