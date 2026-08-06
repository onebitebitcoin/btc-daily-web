import { Fragment } from 'react';
import { CardArt } from '../CardArt';
import { readingDirectionHint, type Card, type Cover } from '../content';
import { SpeakerAvatar } from './SpeakerAvatar';

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

          {/* 표지 콘텐츠는 카드 높이의 절반쯤만 쓴다. 남는 자리에 그날의 인용구를
              넣는다 — 인용구 도입 전 발행분에는 없으므로 있을 때만 그린다. */}
          {cover.quote && (
            <figure className="cover-quote">
              <SpeakerAvatar author={cover.quote.author} portrait={cover.quote.portrait} />
              <blockquote className="cover-quote-text">{cover.quote.text}</blockquote>
              <figcaption className="cover-quote-author">— {cover.quote.author}</figcaption>
            </figure>
          )}
        </div>
      </div>
    </div>
  );
}
