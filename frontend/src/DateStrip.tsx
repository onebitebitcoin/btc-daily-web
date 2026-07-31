import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MonthCalendar } from './Calendar';
import { errorMessage, fetchEditions, type EditionSummary } from './api';
import './calendar.css';

interface DateStripProps {
  activeDate: string;
}

const pillLabel = (date: string) => date.slice(5).replace('-', '.');

export function DateStrip({ activeDate }: DateStripProps) {
  const [editions, setEditions] = useState<EditionSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const activeRef = useRef<HTMLButtonElement>(null);
  const calWrapRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    fetchEditions()
      .then((list) => {
        if (!cancelled) setEditions(list);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ inline: 'center', block: 'nearest' });
  }, [activeDate, editions]);

  useEffect(() => {
    if (!calendarOpen) return;
    const onOutsideClick = (e: MouseEvent) => {
      if (!calWrapRef.current?.contains(e.target as Node)) setCalendarOpen(false);
    };
    document.addEventListener('mousedown', onOutsideClick);
    return () => document.removeEventListener('mousedown', onOutsideClick);
  }, [calendarOpen]);

  if (error) return <nav className="strip strip-error">{error}</nav>;
  if (editions.length === 0) return null;

  return (
    <nav className="strip">
      {editions.map((edition) => {
        const isActive = edition.date === activeDate;
        return (
          <button
            key={edition.date}
            ref={isActive ? activeRef : undefined}
            type="button"
            className={'strip-pill' + (isActive ? ' strip-active' : '')}
            onClick={() => navigate(`/d/${edition.date}`)}
          >
            {pillLabel(edition.date)}
          </button>
        );
      })}
      <div className="strip-cal-wrap" ref={calWrapRef}>
        <button
          type="button"
          className="strip-pill"
          aria-label="달력 보기"
          aria-expanded={calendarOpen}
          onClick={() => setCalendarOpen((open) => !open)}
        >
          <svg
            viewBox="0 0 24 24"
            width="14"
            height="14"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="3" y="5" width="18" height="16" rx="2" />
            <path d="M3 10h18" />
            <path d="M8 3v4" />
            <path d="M16 3v4" />
          </svg>
        </button>
        {calendarOpen && (
          <div className="cal-popover">
            <MonthCalendar
              published={new Set(editions.map((edition) => edition.date))}
              onSelect={(date) => {
                setCalendarOpen(false);
                navigate(`/d/${date}`);
              }}
            />
          </div>
        )}
      </div>
    </nav>
  );
}
