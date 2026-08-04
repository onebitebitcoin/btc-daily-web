/** 에디션 콘텐츠 계약의 타입. 필드 의미는 CONTENT_CONTRACT.md를 따른다.
 *
 *  컴포넌트가 아니라 이 파일에 두는 이유: api.ts와 훅들이 모두 이 타입을 쓰는데
 *  렌더링 컴포넌트에 얹어두면 데이터 계층이 뷰를 import하게 된다.
 */
import type { Theme } from './useThemeVars';

export interface Cover {
  eyebrow: string;
  mark: string[];
  meta: string[];
  hint: string;
}

export interface Card {
  num: number;
  chip: { text: string; emphasis: 'primary' | 'secondary' | null } | null;
  title: string;
  subtitle: string | null;
  chips_label: string | null;
  chips: string[] | null;
  body: string;
  quote: string | null;
  link: { label: string; href: string } | null;
  media: { image: string; href: string | null; cta: string | null } | null;
  qa?: { question: string; answer: string; sources: string[] }[] | null;
}

export interface Closing {
  eyebrow: string;
  mark_lines: string[];
  links: { label: string; href: string }[];
  stamp: string;
  restart: string;
  sources: string[];
  disclaimer: string;
}

export interface EditionContent {
  meta: { title: string; slug: string; date: string };
  theme: Theme;
  brand: string;
  cover: Cover;
  cards: Card[];
  closing: Closing;
}

/** 이 길이를 넘으면 카드에서 본문이 잘린다(feed.css의 -webkit-line-clamp: 7).
 *  본문 규격이 200자 내외라 대부분 걸린다. */
const BODY_CLAMP_CHARS = 150;

/** 가로 데크 시절에 발행된 편들은 표지 힌트가 "옆으로 넘겨서…"로 굳어 있다.
 *  발행분은 다시 쓰지 않으므로(재발행하면 그날 뉴스가 달라진다) 읽는 쪽에서
 *  방향만 바로잡는다. 생성기(fixtures/content.json)는 이미 "위로"로 고쳤다. */
export function readingDirectionHint(hint: string): string {
  return hint.replace(/^옆으로/, '위로');
}

/** 카드 한 장에 다 담기지 않는 내용이 있는가 — 시트를 열 수단을 줄지 판단한다. */
export function hasMoreToRead(card: Card): boolean {
  return (
    card.body.length > BODY_CLAMP_CHARS ||
    Boolean(card.quote) ||
    Boolean(card.qa && card.qa.length > 0)
  );
}
