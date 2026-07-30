import { useCallback, useEffect, useRef, useState } from 'react';

/** Port of the scroll-snap swipe controller from reference/template.html. */
export function useSwipeDeck(total: number) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [current, setCurrent] = useState(0);

  // The reference left `current` entirely to the observer; setting it here too
  // keeps the chrome correct where scrolling or IntersectionObserver is absent.
  const goTo = useCallback(
    (index: number) => {
      const clamped = Math.max(0, Math.min(total - 1, index));
      setCurrent(clamped);
      const slide = trackRef.current?.children[clamped];
      if (!slide) return;
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      slide.scrollIntoView({
        behavior: reduceMotion ? 'auto' : 'smooth',
        inline: 'center',
        block: 'nearest',
      });
    },
    [total],
  );

  const prev = useCallback(() => goTo(current - 1), [goTo, current]);
  const next = useCallback(() => goTo(current + 1), [goTo, current]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') prev();
      else if (e.key === 'ArrowRight') next();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [prev, next]);

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
