import { describe, expect, it } from 'vitest';

import { publishedAgeLabel } from './publishedAge';

const NOW = Date.parse('2026-09-10T12:00:00Z');

describe('publishedAgeLabel', () => {
  it('shows hours for anything published today', () => {
    expect(publishedAgeLabel('2026-09-10T09:00:00Z', NOW)).toBe('3시간 전');
    expect(publishedAgeLabel('2026-09-09T13:00:00Z', NOW)).toBe('23시간 전');
  });

  it('collapses the last hour into 방금', () => {
    expect(publishedAgeLabel('2026-09-10T11:30:00Z', NOW)).toBe('방금');
  });

  it('switches to a date once a day has passed', () => {
    // 몇 주 지난 에디션에 "412시간 전"이 찍히는 것보다 날짜가 읽기 쉽다.
    expect(publishedAgeLabel('2026-09-08T12:00:00Z', NOW)).toBe('9/8');
  });

  it('treats a timestamp without a zone as UTC', () => {
    // 수집기(collect_daily._as_utc)와 같은 규칙 — 파이프라인 양쪽이 같은 시각을 가리킨다.
    expect(publishedAgeLabel('2026-09-10T09:00:00', NOW)).toBe('3시간 전');
  });

  it('honours an explicit offset', () => {
    expect(publishedAgeLabel('2026-09-10T18:00:00+09:00', NOW)).toBe('3시간 전');
  });

  it('reads a future timestamp as 방금 instead of a negative age', () => {
    // 미래로 찍힌 값은 타임존을 잘못 붙인 것이지 앞으로 나올 기사가 아니다.
    expect(publishedAgeLabel('2026-09-10T20:00:00Z', NOW)).toBe('방금');
  });

  it('renders nothing when there is no usable timestamp', () => {
    expect(publishedAgeLabel(null, NOW)).toBeNull();
    expect(publishedAgeLabel(undefined, NOW)).toBeNull();
    expect(publishedAgeLabel('어제', NOW)).toBeNull();
  });
});
