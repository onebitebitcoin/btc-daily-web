import { useCallback, useEffect, useRef, useState } from 'react';

/** 프로그램이 시작한 스크롤이 끝났다고 보기까지 기다리는 최대 시간(ms).
 *
 *  정상 경로에서는 관찰자가 목표 도착을 알려주거나 `scrollend` 가 와서 그 전에 풀린다.
 *  이 타이머는 그 둘이 안 오는 경우(이미 목표에 서 있어 스크롤 자체가 없거나,
 *  scrollend 미지원 브라우저에서 관찰자 임계값을 안 건드릴 만큼 짧게 움직인 경우)를
 *  위한 안전장치다 — 없으면 잠금이 안 풀려 피드가 통째로 멈춘다.
 */
const SETTLE_TIMEOUT_MS = 700;

/** 세로 스냅 피드의 현재 인덱스를 추적하고 이동시킨다.
 *
 *  슬라이드가 뒤로 계속 붙는(무한 피드) 구조라 `total`이 바뀔 때마다 관찰 대상을
 *  다시 등록한다. 시트가 열려 있는 동안에는 키보드 이동을 막아야 시트 안에서
 *  방향키를 누를 때 뒤 피드가 같이 움직이지 않는다.
 *
 *  ## 이동 중 잠금이 필요한 이유
 *
 *  `current` 를 쓰는 주체가 둘이다 — 이동 요청(버튼·키보드)이 낙관적으로 쓰고,
 *  IntersectionObserver 도 쓴다. 스무스 스크롤이 도는 동안 둘이 겹치면 2026-08-23
 *  버튼 도입 뒤 제보된 두 증상이 그대로 난다.
 *
 *  1. **되돌림 → 눌러도 안 넘어간다.** threshold 0.6 을 지나는 순간에는 *떠나는*
 *     슬라이드도 `isIntersecting` 이라 콜백에 같이 실린다. 한 배치 안 엔트리 순서는
 *     명세상 보장이 없어서, 마지막 엔트리를 그대로 쓰면 `current` 가 이전 값으로
 *     되돌아간다. 그러면 다음 클릭이 지금 화면과 같은 인덱스로 가는 제자리 이동이
 *     되어 아무 일도 일어나지 않는다.
 *  2. **두 칸 점프.** 낙관적 `current` 로 다음 목표를 계산하면, 화면이 아직 출발점
 *     근처인데 두 번째 클릭이 `현재+2` 를 노려 한 번에 두 장을 건너뛴다.
 *
 *  그래서 이동을 시작하면 출발·목표를 `pendingRef` 에 적고, 정착할 때까지 (a) 관찰자가
 *  올리는 보고 중 *떠나온* 슬라이드 것만 버리고 (b) 새 이동 요청은 무시한다. 한 번
 *  누르면 정확히 한 장이다.
 *
 *  떠나온 것만 버리는 게 핵심이다. 목표가 아닌 보고를 전부 버리면, 사용자가 버튼을
 *  누른 직후 스와이프로 다른 슬라이드에 가버렸을 때 그 위치를 영영 못 따라잡는다
 *  (실측 확인: 스크롤은 8번인데 활성은 5번에 머물고, 다음 버튼이 6번으로 뒤로 뛴다).
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
      // 이동이 아직 안 끝났으면 새 요청을 받지 않는다 — 받으면 두 칸씩 건너뛴다.
      if (pendingRef.current !== null) return;

      const clamped = Math.max(0, Math.min(total - 1, index));
      setCurrent(clamped);
      const slide = trackRef.current?.children[clamped];
      if (!slide) return;

      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      pendingRef.current = { from: currentRef.current, to: clamped };
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

  const prev = useCallback(() => goTo(current - 1), [goTo, current]);
  const next = useCallback(() => goTo(current + 1), [goTo, current]);

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
  useEffect(() => {
    const track = trackRef.current;
    if (!track || !('onscrollend' in window)) return;
    const onScrollEnd = () => clearSettle();
    track.addEventListener('scrollend', onScrollEnd);
    return () => track.removeEventListener('scrollend', onScrollEnd);
  }, [clearSettle]);

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
        // 떠나온 슬라이드의 늦은 보고만 버린다. 목표든 제3의 위치든 나머지는 받는다 —
        // 버리기만 하면 사용자가 이동 중에 스와이프로 가로챘을 때 그 위치를 영영
        // 못 따라잡고, 다음 버튼이 낡은 인덱스 기준으로 뒤로 점프한다.
        if (pending !== null && index === pending.from) return;
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
