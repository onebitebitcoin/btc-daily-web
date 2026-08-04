import { useCallback, useEffect, useRef, useState } from 'react';

/** 세로 스냅 피드의 현재 인덱스를 추적하고 이동시킨다.
 *
 *  슬라이드가 뒤로 계속 붙는(무한 피드) 구조라 `total`이 바뀔 때마다 관찰 대상을
 *  다시 등록한다. 시트가 열려 있는 동안에는 키보드 이동을 막아야 시트 안에서
 *  방향키를 누를 때 뒤 피드가 같이 움직이지 않는다.
 */
export function useVerticalFeed(total: number, locked = false) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [current, setCurrent] = useState(0);

  const goTo = useCallback(
    (index: number) => {
      const clamped = Math.max(0, Math.min(total - 1, index));
      setCurrent(clamped);
      const slide = trackRef.current?.children[clamped];
      if (!slide) return;
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      slide.scrollIntoView({
        behavior: reduceMotion ? 'auto' : 'smooth',
        block: 'start',
        inline: 'nearest',
      });
    },
    [total],
  );

  const prev = useCallback(() => goTo(current - 1), [goTo, current]);
  const next = useCallback(() => goTo(current + 1), [goTo, current]);

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

  useEffect(() => {
    const track = trackRef.current;
    if (!track || typeof IntersectionObserver === 'undefined') return;
    const slides = Array.from(track.children);
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting && e.intersectionRatio > 0.6) {
            setCurrent(slides.indexOf(e.target));
          }
        });
      },
      { root: track, threshold: [0.6] },
    );
    slides.forEach((s) => io.observe(s));
    return () => io.disconnect();
  }, [total]);

  return { current, trackRef, goTo, prev, next };
}
