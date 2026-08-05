import { cardArtText } from './artText';
import type { Card } from './content';

const pad2 = (n: number) => String(n).padStart(2, '0');

/** 연달아 빈 카드가 나와도 같은 그림으로 보이지 않게 톤을 돌린다(7/27 num 7·8처럼
 *  붙어 나오는 날이 있다). 무작위가 아니라 번호에서 결정되므로 같은 카드는 늘 같다. */
const TONES = 3;

interface CardArtFallbackProps {
  card: Card;
}

/** 이미지가 없는 카드의 아트.
 *
 *  뉴스사 CDN이 대표 이미지를 주지 않는 소스(개발자 포럼·레딧)와, 썸네일이 본문과
 *  어긋나 일부러 뺀 카드가 하루 10장 중 0~3장 나온다. 예전에는 이 자리를 통째로
 *  비웠는데(`return null`), 이미지 영역이 사라지면 카드가 본문만 남아 앞뒤 카드와
 *  리듬이 끊긴다. 가짜 이미지를 채우지 않고(CONTENT_CONTRACT.md 4장) 카드가 이미
 *  가진 문구를 조판해 그 자리를 채운다. */
export function CardArtFallback({ card }: CardArtFallbackProps) {
  const { source, text } = cardArtText(card);

  if (!source) return <div className="art art-blank">{pad2(card.num)}</div>;

  return (
    <div className={`art art-type tone-${card.num % TONES}`}>
      <span className="art-type-wash" aria-hidden="true" />
      {source === 'quote' ? (
        <blockquote className="art-type-line is-quote">
          <span className="art-type-mark" aria-hidden="true">
            “
          </span>
          {text}
        </blockquote>
      ) : (
        <p className="art-type-line is-label">{text}</p>
      )}
    </div>
  );
}
