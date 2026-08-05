import type { Card } from './content';

/** 대체 아트가 무엇을 조판했는지. 카드 본문이 같은 문구를 또 찍지 않도록 알린다. */
export type ArtTextSource = 'quote' | 'subtitle' | 'chip' | null;

export interface ArtText {
  source: ArtTextSource;
  text: string;
}

/** 이미지 없는 카드의 아트에 앉힐 문구를 고른다.
 *
 *  인용이 1순위인 이유는 카드 표면에 나오지 않는 유일한 필드라서다(더보기 시트에만
 *  있다) — 중복 없이 정보가 하나 는다. 나머지 후보는 이미 카드에 찍혀 있으므로,
 *  아트가 가져가면 본문 쪽에서 빼야 같은 말이 두 번 나오지 않는다. */
export function cardArtText(card: Card): ArtText {
  const quote = card.quote?.trim();
  if (quote) return { source: 'quote', text: quote };

  const subtitle = card.subtitle?.trim();
  if (subtitle) return { source: 'subtitle', text: subtitle };

  const chip = card.chip?.text?.trim();
  if (chip) return { source: 'chip', text: chip };

  return { source: null, text: '' };
}

/** 아트가 부제를 이미 크게 조판했으면 본문의 부제 줄은 메아리다. */
export function showsSubtitleInBody(card: Card): boolean {
  if (!card.subtitle) return false;
  if (card.media) return true;
  return cardArtText(card).source !== 'subtitle';
}
