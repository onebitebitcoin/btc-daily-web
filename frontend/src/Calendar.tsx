import { useState } from 'react';

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
const pad = (n: number) => String(n).padStart(2, '0');

interface MonthCalendarProps {
  published: Set<string>;
  onSelect: (date: string) => void;
}

export function MonthCalendar({ published, onSelect }: MonthCalendarProps) {
  const today = new Date();
  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());

  const goPrevMonth = () => {
    if (viewMonth === 0) {
      setViewYear(viewYear - 1);
      setViewMonth(11);
    } else {
      setViewMonth(viewMonth - 1);
    }
  };

  const goNextMonth = () => {
    if (viewMonth === 11) {
      setViewYear(viewYear + 1);
      setViewMonth(0);
    } else {
      setViewMonth(viewMonth + 1);
    }
  };

  const firstDayOffset = new Date(viewYear, viewMonth, 1).getDay();
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const dateStr = (day: number) => `${viewYear}-${pad(viewMonth + 1)}-${pad(day)}`;

  return (
    <div className="cal-body">
      <div className="cal-header">
        <button type="button" className="cal-nav-btn" aria-label="이전 달" onClick={goPrevMonth}>
          &lt;
        </button>
        <span className="cal-title">
          {viewYear}년 {viewMonth + 1}월
        </span>
        <button type="button" className="cal-nav-btn" aria-label="다음 달" onClick={goNextMonth}>
          &gt;
        </button>
      </div>
      <div className="cal-weekdays">
        {WEEKDAYS.map((weekday) => (
          <span key={weekday}>{weekday}</span>
        ))}
      </div>
      <div className="cal-grid">
        {Array.from({ length: firstDayOffset }, (_, i) => (
          <span key={`pad-${i}`} className="cal-day cal-empty" />
        ))}
        {Array.from({ length: daysInMonth }, (_, i) => {
          const day = i + 1;
          const date = dateStr(day);
          if (published.has(date)) {
            return (
              <button
                key={date}
                type="button"
                className="cal-day cal-published"
                onClick={() => onSelect(date)}
              >
                {day}
              </button>
            );
          }
          return (
            <span key={date} className="cal-day cal-empty">
              {day}
            </span>
          );
        })}
      </div>
    </div>
  );
}
