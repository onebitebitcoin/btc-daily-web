import { useEffect, useRef } from 'react';
import type { TrendingItem } from './content';

interface TrendingSheetProps {
  /** null이면 닫힌 상태. */
  item: TrendingItem | null;
  onClose: () => void;
}

/** 트렌딩 한 줄을 펼쳤을 때 그 토픽이 실제로 어떤 기사·영상에서 나왔는지 보여주는 시트.
 *
 *  트렌딩 카드는 10행이 스크롤 없이 딱 들어가도록 높이를 나눠 쓴다(feed.css). 행마다
 *  펼침 영역을 인라인으로 넣으면 그 전제가 깨지고, 세로 스냅 피드 안에 세로 스크롤이
 *  중첩된다 — DetailSheet가 카드 본문에서 이미 피한 문제다. 같은 방식으로 카드 밖에 뺀다.
 */
export function TrendingSheet({ item, onClose }: TrendingSheetProps) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!item) return;
    closeRef.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [item, onClose]);

  if (!item) return null;

  const links = item.links ?? [];

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-label={item.topic}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-grip" />
        <div className="sheet-scroll">
          <h2 className="sheet-title">{item.topic}</h2>
          <p className="trending-sheet-figures">
            {item.mentions}건 · {item.sources}개 매체가 다뤘습니다
          </p>

          {links.length > 0 ? (
            <ul className="trending-sheet-links">
              {links.map((link, i) => (
                <li key={i}>
                  <a
                    className="trending-link"
                    href={link.href}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <span className="trending-link-title">{link.title}</span>
                    {link.source && <span className="trending-link-source">{link.source}</span>}
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="trending-sheet-figures">이 토픽은 원문 목록이 없습니다.</p>
          )}
        </div>
        <button className="sheet-close" type="button" onClick={onClose} ref={closeRef}>
          닫기
        </button>
      </div>
    </div>
  );
}
