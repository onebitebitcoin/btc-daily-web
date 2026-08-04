import { useEffect, useRef } from 'react';
import type { Card } from './content';
import './qa.css';

interface DetailSheetProps {
  /** null이면 닫힌 상태. */
  card: Card | null;
  onClose: () => void;
}

/** 카드에 다 안 들어가는 본문 전문·인용·생각 확장하기를 담는 바텀시트.
 *
 *  세로 스냅 피드 안에 세로 스크롤 카드를 중첩하면 어느 쪽이 스크롤을 먹는지
 *  모바일에서 예측할 수 없다. 넘치는 내용은 카드 밖(이 시트)으로 빼서 축 충돌을
 *  아예 만들지 않는다.
 */
export function DetailSheet({ card, onClose }: DetailSheetProps) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!card) return;
    closeRef.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [card, onClose]);

  if (!card) return null;

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-label={card.title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-grip" />
        <div className="sheet-scroll">
          <h2 className="sheet-title">{card.title}</h2>
          <p className="body-text">{card.body}</p>

          {card.quote && <p className="pull">{'“' + card.quote + '”'}</p>}

          {card.link && (
            <a className="link-cta" href={card.link.href} target="_blank" rel="noopener">
              <span className="tri" />
              {card.link.label}
            </a>
          )}

          {card.qa && card.qa.length > 0 && (
            <div className="qa-block">
              <p className="qa-label">생각 확장하기</p>
              {card.qa.map((q, i) => (
                <details className="qa-item" key={i}>
                  <summary>{q.question}</summary>
                  <p>{q.answer}</p>
                  {q.sources.length > 0 && (
                    <ul className="qa-sources">
                      {q.sources.map((url, si) => (
                        <li key={si}>
                          <a href={url} target="_blank" rel="noopener">
                            출처 {si + 1}
                          </a>
                        </li>
                      ))}
                    </ul>
                  )}
                </details>
              ))}
            </div>
          )}
        </div>
        <button className="sheet-close" type="button" onClick={onClose} ref={closeRef}>
          닫기
        </button>
      </div>
    </div>
  );
}
