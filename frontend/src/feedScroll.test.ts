import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

// vitest 는 CSS 임포트를 스텁으로 처리해서(css: false) `?raw` 도 import.meta.glob 도
// 빈 문자열을 준다. 그래서 파일을 직접 읽는다 — cwd 는 package.json 이 있는 루트다.
const css = readFileSync(resolve(process.cwd(), 'src/feed.css'), 'utf-8');

/** 스와이프가 죽는 CSS 회귀를 잡는다.
 *
 *  jsdom 은 레이아웃도 스크롤 체이닝도 흉내내지 못해 동작으로는 확인할 수 없다.
 *  대신 사고를 냈던 선언 하나를 스타일시트에서 직접 막는다 — 표지 본문에
 *  `overscroll-behavior: contain` 이 들어가면 첫 화면에서 다음 카드로 넘어갈 수
 *  없게 된다(2026-08-23 독자 제보, feed.css 해당 규칙의 주석 참고).
 */
/** 중괄호 블록 단위로 잘라, 셀렉터에 needle 이 들어간 규칙의 본문을 모은다. */
function ruleBodies(needle: string): string[] {
  return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, selector]) => selector.includes(needle))
    .map(([, , body]) => body);
}

describe('표지·클로징 본문 스크롤', () => {
  it('스크롤 전파를 막지 않는다 — 막으면 첫 화면에서 스와이프가 죽는다', () => {
    const bodies = [...ruleBodies('.card.is-cover .card-body'), ...ruleBodies('.card.is-closing .card-body')];

    expect(bodies.length).toBeGreaterThan(0); // 셀렉터 이름이 바뀌면 여기서 먼저 걸린다
    for (const body of bodies) {
      expect(body).not.toMatch(/overscroll-behavior/);
    }
  });

  it('시트는 전파를 막는 게 맞다 — 모달이라 뒤 피드가 따라 움직이면 안 된다', () => {
    const [sheet] = ruleBodies('.sheet-scroll');

    expect(sheet).toMatch(/overscroll-behavior:\s*contain/);
  });
});
