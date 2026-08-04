import { Fragment } from 'react';
import { CardArt } from '../CardArt';
import { readingDirectionHint, type Card, type Cover } from '../content';

interface CoverSlideProps {
  cover: Cover;
  /** 표지 배경으로 쓰는 첫 카드의 이미지. */
  coverCard: Card | undefined;
  date: string;
  media: Record<string, string>;
  isActive: boolean;
  shouldLoadImage: boolean;
  /** 첫 표지가 아니면 앞 날짜에서 넘어온 것 — 날짜 구분선 역할을 겸한다. */
  isDateBreak: boolean;
}

export function CoverSlide({
  cover,
  coverCard,
  date,
  media,
  isActive,
  shouldLoadImage,
  isDateBreak,
}: CoverSlideProps) {
  return (
    <div className={'slide' + (isActive ? ' is-active' : '')} role="group">
      <div className={'card is-cover' + (isDateBreak ? ' is-date-break' : '')}>
        <div className="card-body">
          {isDateBreak && <span className="date-break-rule">여기부터 {date}</span>}
          <span className="badge">{cover.eyebrow}</span>
          {coverCard && (
            <div className="cover-art">
              <CardArt
                card={coverCard}
                date={date}
                media={media}
                shouldLoad={shouldLoadImage}
              />
            </div>
          )}
          <h1 className="cover-mark">
            {cover.mark.map((line, i) => (
              <Fragment key={i}>
                {i > 0 && <br />}
                {line}
              </Fragment>
            ))}
          </h1>
          <p className="cover-meta">
            {cover.meta.map((x, i) => (
              <span key={i}>{x}</span>
            ))}
          </p>
          <div className="cover-hint">
            {readingDirectionHint(cover.hint)}{' '}
            <span className="sw">
              <span />
              <span />
              <span />
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
