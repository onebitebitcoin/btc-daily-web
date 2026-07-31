import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { StatusScreen } from './EditionPage';
import { MonthCalendar } from './Calendar';
import { errorMessage, fetchEditions } from './api';
import './calendar.css';

export default function CalendarPage() {
  const [published, setPublished] = useState<Set<string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    fetchEditions()
      .then((list) => {
        if (!cancelled) setPublished(new Set(list.map((edition) => edition.date)));
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <StatusScreen>{error}</StatusScreen>;
  if (!published) return <StatusScreen>불러오는 중…</StatusScreen>;

  return (
    <div className="calendar-shell">
      <MonthCalendar published={published} onSelect={(date) => navigate(`/d/${date}`)} />
    </div>
  );
}
