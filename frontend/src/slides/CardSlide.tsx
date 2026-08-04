import { CardArt } from '../CardArt';
import { hasMoreToRead, type Card } from '../content';

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
            </span>
            {card.chip && (
              <span className={'badge' + emphClass(card.chip.emphasis)}>{card.chip.text}</span>
            )}
          </div>

          <div className="titles">
            <div className="primary">{card.title}</div>
            {card.subtitle && <div className="secondary">{card.subtitle}</div>}
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
