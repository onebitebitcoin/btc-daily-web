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
}

export function CardSlide({
  card,
  date,
  total,
  media,
  isActive,
  shouldLoadImage,
  onOpenDetail,
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
