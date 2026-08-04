import { cardImageSrc } from './imageUrl';
import type { Card } from './content';

const pad2 = (n: number) => String(n).padStart(2, '0');

interface CardArtProps {
  card: Card;
  date: string;
  media: Record<string, string>;
  /** 로딩 창(현재 인덱스 ±2) 밖이면 false — src를 아예 붙이지 않는다.
   *
   *  `loading="lazy"`만으로는 부족하다. 스냅 스크롤로 빠르게 내리면 브라우저가
   *  뷰포트 근처 이미지를 전부 받아버려서, 3장만 보고 나가도 하루치를 다 받는다. */
  shouldLoad: boolean;
}

export function CardArt({ card, date, media, shouldLoad }: CardArtProps) {
  if (!card.media) return null;

  const src = cardImageSrc(date, card.num, card.media.image, media);
  if (!src || !shouldLoad) {
    return (
      <div className="art art-blank" aria-hidden={!src ? undefined : 'true'}>
        {pad2(card.num)}
      </div>
    );
  }

  const img = (
    <>
      {/* 원본을 자르지 않고(contain) 보여주면 띠의 남는 자리가 빈 색면으로 남는다.
          같은 이미지를 흐리게 깔아 그 자리를 메운다 — 브라우저 캐시를 그대로
          재사용하므로 추가로 받는 바이트는 없다. */}
      <span className="art-fill" style={{ backgroundImage: `url("${src}")` }} aria-hidden="true" />
      <img src={src} alt={card.title} loading="lazy" decoding="async" />
    </>
  );
  const badge =
    card.media.href && card.media.cta ? (
      <span className="art-badge">
        <span className="tri" />
        {card.media.cta}
      </span>
    ) : null;

  return card.media.href ? (
    <a className="art is-link" href={card.media.href} target="_blank" rel="noopener">
      {img}
      {badge}
    </a>
  ) : (
    <div className="art">{img}</div>
  );
}
