import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { errorMessage, fetchEdition, fetchEditions } from './api';
import type { EditionContent } from './content';

/** 무한 피드가 한 세션에서 이어붙일 수 있는 최대 에디션 수.
 *
 *  하루치가 슬라이드 12장이라 7일이면 84장이 DOM에 남는다. 그 이상은 가상화가
 *  필요한데 스냅 스크롤에서 앞쪽을 언마운트하면 스크롤 위치 보정이 까다롭다.
 *  더 과거는 캘린더로 점프하게 두는 편이 단순하고 데이터도 아낀다.
 */
export const MAX_FEED_EDITIONS = 7;

export interface FeedEntry {
  date: string;
  /** 로드에 실패하면 null — 그 날짜만 에러 슬라이드가 되고 피드는 계속된다. */
  content: EditionContent | null;
  error: string | null;
}

/** 시작 날짜부터 과거로 이어지는 에디션 큐를 관리한다.
 *
 *  다음 날짜는 **JSON만** 미리 받아둔다. 이미지는 그 날짜 슬라이드에 실제로
 *  진입한 뒤에야 요청되므로, 끝까지 안 내려가면 그만큼 안 받는다.
 */
export function useEditionQueue(startDate: string, maxEditions: number = MAX_FEED_EDITIONS) {
  const [publishedDates, setPublishedDates] = useState<string[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [entries, setEntries] = useState<FeedEntry[]>([]);
  const cache = useRef(new Map<string, Promise<EditionContent>>());

  useEffect(() => {
    let cancelled = false;
    fetchEditions()
      .then((list) => {
        if (cancelled) return;
        // API는 오름차순으로 준다. 피드는 최신에서 과거로 내려가므로 뒤집는다.
        setPublishedDates(list.map((e) => e.date).sort().reverse());
      })
      .catch((err: unknown) => {
        if (!cancelled) setListError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /** 피드에 등장할 날짜 순서. 시작 날짜가 목록에 없어도(직접 URL 입력) 시도는 한다. */
  const feedDates = useMemo(() => {
    if (!publishedDates) return null;
    const older = publishedDates.filter((d) => d < startDate);
    return [startDate, ...older].slice(0, maxEditions);
  }, [publishedDates, startDate, maxEditions]);

  const request = useCallback((date: string) => {
    const cached = cache.current.get(date);
    if (cached) return cached;
    const pending = fetchEdition(date).catch((err: unknown) => {
      // 실패한 프라미스를 캐시에 남기면 영영 재시도하지 못한다.
      cache.current.delete(date);
      throw err;
    });
    cache.current.set(date, pending);
    return pending;
  }, []);

  const appendDate = useCallback(
    async (date: string) => {
      const settle = (entry: FeedEntry) =>
        setEntries((prev) => (prev.some((e) => e.date === date) ? prev : [...prev, entry]));
      try {
        settle({ date, content: await request(date), error: null });
      } catch (err: unknown) {
        settle({ date, content: null, error: errorMessage(err) });
      }
    },
    [request],
  );

  useEffect(() => {
    setEntries([]);
  }, [startDate]);

  useEffect(() => {
    if (!feedDates || feedDates.length === 0 || entries.length > 0) return;
    void appendDate(feedDates[0]);
  }, [feedDates, entries.length, appendDate]);

  // 다음 날짜 JSON 선반영 — 13KB(gzip)라 미리 받아도 부담이 없고, 클로징에
  // 도달했을 때 빈 화면이 뜨지 않는다.
  useEffect(() => {
    const nextDate = feedDates?.[entries.length];
    if (!nextDate) return;
    void request(nextDate).catch(() => undefined);
  }, [feedDates, entries.length, request]);

  const loadMore = useCallback(() => {
    const nextDate = feedDates?.[entries.length];
    if (nextDate) void appendDate(nextDate);
  }, [feedDates, entries.length, appendDate]);

  const hasMore = feedDates !== null && entries.length < feedDates.length;
  /** 상한에 걸려 더 못 내려가는 상태 — 과거가 남았는데 피드를 끊은 경우다. */
  const cappedByLimit =
    publishedDates !== null &&
    !hasMore &&
    publishedDates.filter((d) => d < startDate).length + 1 > maxEditions;

  return { entries, loadMore, hasMore, cappedByLimit, listError, publishedDates };
}
