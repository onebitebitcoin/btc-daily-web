import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { errorMessage, fetchLikes, likeCard, unlikeCard } from './api';
import { likedNums, setLiked } from './likeStorage';

/** 좋아요 하나를 가리키는 키. 카드 번호는 에디션 안에서만 유일해서 날짜가 붙어야 한다. */
export const likeKey = (date: string, num: number) => `${date}:${num}`;

/** 피드에 실린 여러 날짜의 좋아요를 한자리에서 관리한다.
 *
 *  피드는 과거로 끝없이 이어지며 여러 에디션이 한 화면에 섞여 있다. 그래서 날짜 하나가
 *  아니라 지금 실려 있는 날짜 전부를 받아, 새로 붙은 날짜만 추가로 조회한다. 이미 받은
 *  날짜를 `loadedRef` 로 기억하므로 위아래로 오가도 같은 날짜를 다시 요청하지 않는다.
 *
 *  수치는 서버가, "내가 눌렀다"는 기억은 브라우저가 갖는다(`likeStorage`). 둘을 한자리에
 *  모아 카드가 한 번에 읽을 수 있게 한다.
 *
 *  누르면 화면 숫자를 먼저 올리고 요청을 보낸다. 실패하면 숫자와 저장소를 원래대로
 *  되돌리고 메시지를 띄운다 — 조용히 되돌아가면 사용자는 자기가 잘못 눌렀다고 생각한다.
 */
export function useCardLikes(dates: string[]) {
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [mine, setMine] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState<string | null>(null);
  const loadedRef = useRef<Set<string>>(new Set());

  // 배열 참조가 매 렌더 바뀌어도 내용이 같으면 effect 를 다시 돌리지 않게 한다.
  const dateKey = dates.join(',');
  const dateList = useMemo(() => dates, [dateKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let cancelled = false;
    const fresh = dateList.filter((date) => !loadedRef.current.has(date));
    if (fresh.length === 0) return;
    fresh.forEach((date) => loadedRef.current.add(date));

    setMine((prev) => {
      const next = new Set(prev);
      for (const date of fresh) {
        for (const num of likedNums(date)) next.add(likeKey(date, num));
      }
      return next;
    });

    for (const date of fresh) {
      fetchLikes(date)
        .then((loaded) => {
          if (cancelled) return;
          setCounts((prev) => {
            const next = { ...prev };
            for (const [num, count] of Object.entries(loaded)) next[`${date}:${num}`] = count;
            return next;
          });
        })
        .catch(() => {
          // 좋아요 수를 못 받아도 카드는 읽을 수 있어야 한다. 숫자만 비워 둔다.
          // 다시 시도하려고 loadedRef 에서 빼지는 않는다 — 실패가 이어지면 스크롤할
          // 때마다 요청이 반복돼 더 나빠진다.
        });
    }

    return () => {
      cancelled = true;
    };
  }, [dateList]);

  const toggle = useCallback(
    async (date: string, num: number) => {
      const key = likeKey(date, num);
      const liked = mine.has(key);
      const before = counts[key] ?? 0;

      setCounts((prev) => ({ ...prev, [key]: Math.max(0, before + (liked ? -1 : 1)) }));
      setMine((prev) => {
        const next = new Set(prev);
        if (liked) next.delete(key);
        else next.add(key);
        return next;
      });
      setLiked(date, num, !liked);
      setError(null);

      try {
        const result = liked ? await unlikeCard(date, num) : await likeCard(date, num);
        // 서버가 센 값이 진짜다. 같은 순간 다른 사람이 눌렀으면 여기서 맞춰진다.
        setCounts((prev) => ({ ...prev, [key]: result.count }));
      } catch (err) {
        setCounts((prev) => ({ ...prev, [key]: before }));
        setMine((prev) => {
          const next = new Set(prev);
          if (liked) next.add(key);
          else next.delete(key);
          return next;
        });
        setLiked(date, num, liked);
        setError(errorMessage(err));
      }
    },
    [counts, mine],
  );

  return { counts, mine, error, toggle, clearError: useCallback(() => setError(null), []) };
}
