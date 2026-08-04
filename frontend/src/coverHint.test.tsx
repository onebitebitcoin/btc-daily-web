import { describe, expect, it } from 'vitest';
import { readingDirectionHint } from './content';

describe('readingDirectionHint', () => {
  it('rewrites the horizontal-deck wording published before the vertical feed', () => {
    expect(readingDirectionHint('옆으로 넘겨서 오늘의 비트코인 이슈 10건 보기')).toBe(
      '위로 넘겨서 오늘의 비트코인 이슈 10건 보기',
    );
  });

  it('leaves a hint that already says 위로 alone', () => {
    const hint = '위로 넘겨서 오늘의 비트코인 이슈 10건 보기';

    expect(readingDirectionHint(hint)).toBe(hint);
  });

  it('only rewrites the leading direction word, not a mention elsewhere', () => {
    expect(readingDirectionHint('카드를 옆으로 두고 보기')).toBe('카드를 옆으로 두고 보기');
  });
});
