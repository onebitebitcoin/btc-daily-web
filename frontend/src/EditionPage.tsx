import { useEffect, useState, type ReactNode } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { CardDeck, type EditionContent } from './CardDeck';
import { DateStrip } from './DateStrip';
import { NotFoundError, errorMessage, fetchEdition, fetchLatestEdition } from './api';
import { bundledMedia } from './media';
import './strip.css';

export function StatusScreen({ children }: { children: ReactNode }) {
  return <div className="status-screen">{children}</div>;
}

/** `/` has no date yet — fetch the latest edition just to learn its date, then
 *  hand off to the real route so EditionPage below is the single fetch path. */
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
  const { date } = useParams<{ date: string }>();
  const [content, setContent] = useState<EditionContent | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!date) return;
    setContent(null);
    setError(null);
    let cancelled = false;
    fetchEdition(date)
      .then((edition) => {
        if (!cancelled) setContent(edition);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [date]);

  if (!date) return <StatusScreen>잘못된 경로입니다.</StatusScreen>;
  if (error) return <StatusScreen>{error}</StatusScreen>;
  if (!content) return <StatusScreen>불러오는 중…</StatusScreen>;

  return (
    <div className="shell">
      <DateStrip activeDate={date} />
      <CardDeck content={content} media={bundledMedia} />
    </div>
  );
}
