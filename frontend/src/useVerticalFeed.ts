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
 *  ## 이동 수단은 버튼과 키보드뿐이다
 *
 *  2026-09-18 부터 트랙의 세로 스크롤을 CSS 에서 막았다(feed.css 의 `.feed-track`).
 *  터치 스와이프와 휠은 브라우저 네이티브 스냅이 처리했는데, 애니메이션 도중에
 *  손가락이 닿으면 그 자리에서 멈추고 따라와 카드가 두 장 사이에 걸치거나 엉뚱한
 *  카드로 넘어갔다. 그 판정을 우리가 가져오려는 시도도 더 불안정했다. 지금은 모든
 *  이동이 `goTo` 한 곳을 지나므로 언제 어디로 가는지가 한 자리에서 결정된다.
 *
 *  프로그램이 부르는 `scrollIntoView` 는 `overflow: hidden` 에서도 그대로 동작한다.
 *  막히는 것은 사용자 입력뿐이다.
 *
 *  ## 이동 중에는 새 요청을 받지 않는다
 *
 *  `goTo` 는 앞 이동이 정착할 때까지 새 요청을 버린다. 버튼은 그동안 `moving` 으로
 *  비활성이 되어 눌리지 않는 게 눈에 보이지만, 키보드와 진행바 탭도 같은 경로를
 *  타므로 훅 안에서도 막는다.
 *
 *  잠금은 `scrollend` 나 타이머가 푼다. IntersectionObserver 는 풀지 않는다 —
 *  관찰자는 임계값(60%)을 지나는 순간 보고하는데 그때 화면은 아직 움직이는 중이라,
 *  거기서 버튼이 살아나면 애니메이션이 끝나기 전에 다음 이동이 겹쳐 시작된다.
 *
 *  ## 관찰자 보고를 거르는 이유
 *
 *  `current` 를 쓰는 주체가 둘이다 — `goTo` 가 낙관적으로 쓰고, 관찰자도 쓴다.
 *  threshold 0.6 을 지나는 순간에는 *떠나는* 슬라이드도 `isIntersecting` 이라 콜백에
 *  같이 실리고, 한 배치 안 엔트리 순서는 명세상 보장이 없다. 마지막 엔트리를 그대로
 *  쓰면 `current` 가 이전 값으로 되돌아가고, 그러면 다음 클릭이 지금 화면과 같은
 *  인덱스로 가는 제자리 이동이 되어 아무 일도 일어나지 않는다(2026-08-23 제보).
 *
 *  그래서 이동을 시작하면 출발·목표를 `pendingRef` 에 적고, 그 구간을 지나가는 보고를
 *  버린다. 구간 밖 보고는 받는다 — 딥링크 점프나 캘린더 이동처럼 화면이 멀리 뛴 경우다.
 */
export function useVerticalFeed(total: number, locked = false) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [current, setCurrent] = useState(0);
  /** 이동 중이면 출발·목표 인덱스, 정착했으면 null. */
  const pendingRef = useRef<{ from: number; to: number } | null>(null);
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** 이동 애니메이션이 도는 중인지. 버튼을 비활성으로 만들려고 state 로 둔다. */
  const [moving, setMoving] = useState(false);
  // goTo 안에서 출발점을 읽으려고 둔다. state 를 직접 읽으면 슬라이드가 바뀔 때마다
  // goTo 가 새로 만들어지고, 그걸 의존하는 키보드 리스너까지 매번 다시 붙는다.
  const currentRef = useRef(0);
  currentRef.current = current;

  const clearSettle = useCallback(() => {
    pendingRef.current = null;
    setMoving(false);
    if (settleTimerRef.current !== null) {
      clearTimeout(settleTimerRef.current);
      settleTimerRef.current = null;
    }
  }, []);

  const goTo = useCallback(
    (index: number) => {
      // 이동이 끝나기 전에는 새 요청을 받지 않는다. 버튼도 그동안 비활성이라
      // 눌리지 않지만, 키보드와 진행바 탭도 같은 경로를 타므로 여기서 막는다.
      if (pendingRef.current !== null) return;

      const clamped = Math.max(0, Math.min(total - 1, index));
      setCurrent(clamped);
      const slide = trackRef.current?.children[clamped];
      if (!slide) return;

      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      pendingRef.current = { from: currentRef.current, to: clamped };
      setMoving(true);
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

  const step = useCallback((delta: number) => goTo(currentRef.current + delta), [goTo]);

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
        // 잠금을 여기서 풀지 않는다. 관찰자는 임계값(60%)을 지나는 순간 보고하는데,
        // 그때 화면은 아직 움직이는 중이다. 버튼이 거기서 살아나면 애니메이션이
        // 끝나기 전에 다음 이동이 겹쳐 시작된다. 해제는 scrollend 와 타이머가 맡는다.
        setCurrent(index);
      },
      { root: track, threshold: [0.6] },
    );
    slides.forEach((s) => io.observe(s));
    return () => io.disconnect();
  }, [total, clearSettle]);

  return { current, moving, trackRef, goTo, prev, next };
}
