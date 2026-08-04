import { useEffect, useState } from 'react';
import { MonthCalendar } from './Calendar';
import hanipLogo from './assets/brand/hanip-logo.jpg';
import './chrome.css';
import './calendar.css';

const chipLabel = (date: string) => date.slice(5).replace('-', '.');

interface FeedChromeProps {
  brand: string;
  /** 현재 슬라이드가 속한 에디션의 날짜. */
  date: string;
  /** 그 에디션 안에서의 위치(0 = 표지). */
  localIndex: number;
  localTotal: number;
  publishedDates: string[] | null;
  onGoToLocal: (index: number) => void;
  onSelectDate: (date: string) => void;
}

/** 피드 위에 얹히는 고정 크롬 — 진행바, 브랜드, 날짜 칩.
 *
 *  진행바는 **현재 에디션의 슬라이드만** 보여준다. 피드는 과거로 무한히
 *  이어지므로 전체를 한 줄에 담을 수 없고, 날짜 경계를 넘으면 리셋된다.
 */
export function FeedChrome({
  brand,
  date,
  localIndex,
  localTotal,
  publishedDates,
  onGoToLocal,
  onSelectDate,
}: FeedChromeProps) {
  const [calendarOpen, setCalendarOpen] = useState(false);

  useEffect(() => {
    if (!calendarOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setCalendarOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [calendarOpen]);

  return (
    <>
      <div className="progress-bar">
        {Array.from({ length: localTotal }, (_, i) => (
          <i key={i} className={i <= localIndex ? 'done' : undefined} onClick={() => onGoToLocal(i)}>
            <b />
          </i>
        ))}
      </div>

      <div className="topline">
        <span className="brand">
          <img className="brand-logo" src={hanipLogo} alt="" />
          {brand}
        </span>
        <button
          type="button"
          className="date-chip"
          aria-label="날짜 선택"
          aria-expanded={calendarOpen}
          onClick={() => setCalendarOpen((open) => !open)}
        >
          {chipLabel(date)}
          <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>
      </div>

      {calendarOpen && (
        <div className="sheet-backdrop" onClick={() => setCalendarOpen(false)}>
          <div
            className="sheet cal-sheet"
            role="dialog"
            aria-modal="true"
            aria-label="날짜 선택"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sheet-grip" />
            <MonthCalendar
              published={new Set(publishedDates ?? [])}
              onSelect={(picked) => {
                setCalendarOpen(false);
                onSelectDate(picked);
              }}
            />
            <button className="sheet-close" type="button" onClick={() => setCalendarOpen(false)}>
              닫기
            </button>
          </div>
        </div>
      )}
    </>
  );
}
