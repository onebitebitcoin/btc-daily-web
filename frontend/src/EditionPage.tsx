import { useEffect, useState, type ReactNode } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { ShortsFeed } from './ShortsFeed';
import { NotFoundError, errorMessage, fetchLatestEdition } from './api';
import './chrome.css';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function StatusScreen({ children }: { children: ReactNode }) {
  return <div className="status-screen">{children}</div>;
}

/** `/` has no date yet — fetch the latest edition just to learn its date, then
 *  hand off to the real route so the feed has a concrete starting point. */
export function RootRedirect() {
  const [date, setDate] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchLatestEdition()
      .then((edition) => {
        if (!cancelled) setDate(edition.meta.date);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof NotFoundError ? '아직 발행된 데이터가 없습니다.' : errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <StatusScreen>{error}</StatusScreen>;
  if (!date) return <StatusScreen>불러오는 중…</StatusScreen>;
  return <Navigate to={`/d/${date}`} replace />;
}

export default function EditionPage() {
  const { date, index } = useParams<{ date: string; index?: string }>();

  if (!date || !ISO_DATE.test(date)) return <StatusScreen>잘못된 경로입니다.</StatusScreen>;

  // 인덱스는 공유 링크에서만 오는 선택 값이다. 숫자가 아니면 표지에서 시작한다.
  const parsed = Number(index);
  const startIndex = Number.isInteger(parsed) && parsed > 0 ? parsed : 0;

  return <ShortsFeed startDate={date} startIndex={startIndex} />;
}
