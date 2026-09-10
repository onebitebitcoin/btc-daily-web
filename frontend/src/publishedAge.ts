/** 카드가 링크한 기사가 얼마나 새 소식인지 한 줄로 조판한다. */

const HOUR = 3600_000;
const DAY = 24 * HOUR;

/**
 * ISO 문자열 → "3시간 전" 같은 라벨. 못 읽으면 null(그 줄을 아예 안 그린다).
 *
 * 하루가 넘으면 상대 표기 대신 날짜를 준다. 발행 당일에는 전부 24시간 안이라
 * "N시간 전"으로 나오고, 지난 발행분을 나중에 열면 "9/10" 처럼 날짜가 보인다 —
 * 몇 주 지난 에디션에 "412시간 전"이 찍히는 것보다 읽기 쉽다.
 *
 * tz 표기가 없는 값은 UTC 로 본다. 수집기(collect_daily._as_utc)와 같은 규칙이라
 * 파이프라인 양쪽이 같은 시각을 가리킨다.
 */
export function publishedAgeLabel(iso: string | null | undefined, now: number): string | null {
  if (!iso) return null;
  const normalized = /([zZ]|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`;
  const t = Date.parse(normalized);
  if (Number.isNaN(t)) return null;

  const diff = now - t;
  // 미래로 찍힌 값은 타임존을 잘못 붙인 것이다. "-3시간 전"을 보여주느니 방금으로 둔다.
  if (diff < HOUR) return '방금';
  if (diff < DAY) return `${Math.floor(diff / HOUR)}시간 전`;

  const d = new Date(t);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}
