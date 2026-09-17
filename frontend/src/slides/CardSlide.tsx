import { CardArt } from '../CardArt';
import { showsSubtitleInBody } from '../artText';
import { hasMoreToRead, type Card } from '../content';
import { publishedAgeLabel } from '../publishedAge';

const pad2 = (n: number) => String(n).padStart(2, '0');

const emphClass = (emphasis: string | null) =>
  emphasis === 'primary' ? ' emph-a' : emphasis === 'secondary' ? ' emph-b' : '';

interface CardSlideProps {
  card: Card;
  date: string;
  total: number;
  media: Record<string, string>;
  isActive: boolean;
  shouldLoadImage: boolean;
  onOpenDetail: () => void;
  /** 이 카드에 쌓인 좋아요 수. 0이면 숫자를 감추고 아이콘만 보인다. */
  likeCount: number;
  /** 이 브라우저가 눌렀는지. 서버가 아니라 localStorage 가 기억한다. */
  liked: boolean;
  onToggleLike: () => void;
  onShare: () => void;
}

export function CardSlide({
  card,
  date,
  total,
  media,
  isActive,
  shouldLoadImage,
  onOpenDetail,
  likeCount,
  liked,
  onToggleLike,
  onShare,
}: CardSlideProps) {
  // 렌더 시점을 기준으로 잡는다. 발행 당일에는 전부 "N시간 전"으로 나오고,
  // 지난 에디션을 나중에 열면 날짜로 바뀐다(publishedAgeLabel 주석 참고).
  const age = publishedAgeLabel(card.published_at, Date.now());

  return (
    <div className={'slide' + (isActive ? ' is-active' : '')} role="group">
      <div className="card">
        <div className="card-art">
          <CardArt card={card} date={date} media={media} shouldLoad={shouldLoadImage} />
        </div>

        <div className="card-body">
          <div className="card-head">
            <span className="card-num">
              {pad2(card.num)} / {total}
              {age && <span className="card-age">{age}</span>}
            </span>
            {card.chip && (
              <span className={'badge' + emphClass(card.chip.emphasis)}>{card.chip.text}</span>
            )}
          </div>

          <div className="titles">
            <div className="primary">{card.title}</div>
            {showsSubtitleInBody(card) && <div className="secondary">{card.subtitle}</div>}
          </div>

          {card.chips && card.chips.length > 0 && (
            <div className="chips-row">
              {card.chips_label && <span className="cl">{card.chips_label}</span>}
              {card.chips.map((c, i) => (
                <span className="chip" key={i}>
                  {c}
                </span>
              ))}
            </div>
          )}

          <p className="body-text is-clamped">{card.body}</p>

          <div className="card-actions">
            <button
              type="button"
              className={'act-btn' + (liked ? ' is-on' : '')}
              onClick={onToggleLike}
              aria-pressed={liked}
              aria-label={liked ? '좋아요 취소' : '좋아요'}
            >
              <HeartIcon filled={liked} />
              {likeCount > 0 && <span className="act-count">{likeCount}</span>}
            </button>
            <button
              type="button"
              className="act-btn"
              onClick={onShare}
              aria-label="이 카드 링크 공유"
            >
              <ShareIcon />
            </button>
            {hasMoreToRead(card) && (
              <button className="more-btn" type="button" onClick={onOpenDetail}>
                더보기
              </button>
            )}
            {card.link && (
              <a className="link-cta" href={card.link.href} target="_blank" rel="noopener">
                <span className="tri" />
                {card.link.label}
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** 아이콘은 인라인 SVG로 둔다 — 이모지 금지 규칙이 있고, 이 둘 때문에
 *  아이콘 라이브러리를 물리면 번들만 늘어난다(FeedNav.tsx와 같은 판단). */
function HeartIcon({ filled }: { filled: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" focusable="false">
      <path
        d="M12 20.7l-1.3-1.19C5.9 15.2 3 12.5 3 9.2 3 6.6 5 4.7 7.5 4.7c1.4 0 2.8.67 3.7 1.73l.8.95.8-.95c.9-1.06 2.3-1.73 3.7-1.73C19 4.7 21 6.6 21 9.2c0 3.3-2.9 6-7.7 10.31L12 20.7z"
        fill={filled ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ShareIcon() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" focusable="false">
      <path
        d="M12 15V3.5M12 3.5L8.2 7.3M12 3.5l3.8 3.8M5 13.5V18a2 2 0 002 2h10a2 2 0 002-2v-4.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
