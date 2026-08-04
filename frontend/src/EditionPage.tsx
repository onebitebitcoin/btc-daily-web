import { useEffect, useState, type ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import { ShortsFeed } from './ShortsFeed';
import { errorMessage, fetchEditions } from './api';
import './chrome.css';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function StatusScreen({ children }: { children: ReactNode }) {
  return <div className="status-screen">{children}</div>;
}

/** `/`에서 최신 편부터 시작하는 피드.
 *
 *  일부러 리다이렉트하지 않는다. `/d/{최신날짜}`로 튕기면 그 상태에서 북마크한
 *  사람은 그날 날짜에 고정된 북마크를 갖게 되고, 다음 날 열어도 지난 편을 본다.
 *  `/`를 그대로 두어야 "항상 최신"으로 북마크된다.
 */
export function LatestFeed() {
  const [date, setDate] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // 목록(1KB 미만)만으로 최신 날짜를 알 수 있다. 최신 에디션 본문(50KB)을 받아
    // 날짜만 꺼내 쓰면 그만큼을 버리는 셈이다. 목록은 피드가 어차피 다시 쓴다.
    fetchEditions()
      .then((list) => {
        if (cancelled) return;
        if (list.length === 0) {
          setError('아직 발행된 데이터가 없습니다.');
          return;
        }
        setDate(list[list.length - 1].date);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <StatusScreen>{error}</StatusScreen>;
  if (!date) return <StatusScreen>불러오는 중…</StatusScreen>;
  return <ShortsFeed startDate={date} startIndex={0} />;
}

/** `/d/:date` — 특정 날짜부터 시작하는 피드. 공유 링크와 캘린더가 쓴다. */
export default function EditionPage() {
  const { date, index } = useParams<{ date: string; index?: string }>();

  if (!date || !ISO_DATE.test(date)) return <StatusScreen>잘못된 경로입니다.</StatusScreen>;

  // 인덱스는 공유 링크에서만 오는 선택 값이다. 숫자가 아니면 표지에서 시작한다.
  const parsed = Number(index);
  const startIndex = Number.isInteger(parsed) && parsed > 0 ? parsed : 0;

  return <ShortsFeed startDate={date} startIndex={startIndex} />;
}
