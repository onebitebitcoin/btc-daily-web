import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { CoverSlide } from './slides/CoverSlide';
import { SpeakerAvatar } from './slides/SpeakerAvatar';
import { speakerShortName, type Cover, type CoverQuote } from './content';

// TrendingSlide.test.tsx 와 같은 이유로 slides/ 밖에 둔다 — 컴포넌트 파일에서
// 헬퍼를 export 하면 eslint react-refresh/only-export-components 가 경고한다.

const COVER: Cover = {
  eyebrow: '24시간 다이제스트',
  mark: ['8월 8일', '비트코인 카드뉴스'],
  meta: ['최근 24시간 수집', '뉴스 + 유튜브', '2026.08.08'],
  hint: '위로 넘겨서 오늘의 비트코인 이슈 10건 보기',
};

const QUOTE: CoverQuote = {
  id: 'mises-boom-collapse',
  text: '신용 확장이 만들어낸 호황은 끝내 붕괴를 피할 방법이 없다.',
  author: '루트비히 폰 미제스',
  portrait: null,
};

function renderCover(cover: Cover) {
  return render(
    <CoverSlide
      cover={cover}
      coverCard={undefined}
      date="2026-08-08"
      media={{}}
      isActive
      shouldLoadImage={false}
      isDateBreak={false}
    />,
  );
}

describe('speakerShortName', () => {
  it('keeps the last word so every author in the pool shortens to a surname', () => {
    expect(speakerShortName('루트비히 폰 미제스')).toBe('미제스');
    expect(speakerShortName('프리드리히 하이에크')).toBe('하이에크');
    expect(speakerShortName('오이겐 폰 뵘바베르크')).toBe('뵘바베르크');
    expect(speakerShortName('카를 멩거')).toBe('멩거');
    expect(speakerShortName('머리 로스바드')).toBe('로스바드');
    expect(speakerShortName('헨리 해즐릿')).toBe('해즐릿');
  });

  it('falls back to the whole name when there is no space', () => {
    expect(speakerShortName('미제스')).toBe('미제스');
  });
});

describe('SpeakerAvatar', () => {
  it('shows the portrait when the stem is bundled', () => {
    const { container } = render(
      <SpeakerAvatar author="카를 멩거" portrait="menger" portraits={{ menger: '/menger.jpg' }} />,
    );

    const img = container.querySelector('img.speaker-avatar');
    expect(img?.getAttribute('src')).toBe('/menger.jpg');
    // 바로 아래 figcaption 에 이름이 글자로 있어 읽어주면 중복된다.
    expect(img?.getAttribute('aria-hidden')).toBe('true');
    expect(img?.getAttribute('alt')).toBe('');
  });

  it('types the name when the person has no public-domain portrait', () => {
    const { container } = render(
      <SpeakerAvatar author="루트비히 폰 미제스" portrait={null} portraits={{}} />,
    );

    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('.speaker-avatar.is-type')?.textContent).toBe('미제스');
  });

  it('types the name when the stem is set but the asset is missing', () => {
    // 데이터에 stem 이 남았는데 파일을 지운 경우 — 깨진 이미지 대신 아바타로 떨어진다.
    const { container } = render(
      <SpeakerAvatar author="카를 멩거" portrait="menger" portraits={{}} />,
    );

    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('.speaker-avatar.is-type')?.textContent).toBe('멩거');
  });
});

describe('CoverSlide', () => {
  it('renders the quote and its author under the swipe hint', () => {
    const { container } = renderCover({ ...COVER, quote: QUOTE });

    expect(container.querySelector('.cover-quote-text')?.textContent).toBe(QUOTE.text);
    expect(container.querySelector('.cover-quote-author')?.textContent).toBe(
      '— 루트비히 폰 미제스',
    );
  });

  it('draws nothing extra for editions published before the quote existed', () => {
    const { container } = renderCover(COVER);

    expect(container.querySelector('.cover-quote')).toBeNull();
  });

  it('treats an explicit null quote the same as an absent one', () => {
    const { container } = renderCover({ ...COVER, quote: null });

    expect(container.querySelector('.cover-quote')).toBeNull();
  });

  it('keeps the date and the swipe hint alongside the quote', () => {
    const { container } = renderCover({ ...COVER, quote: QUOTE });

    expect(container.querySelector('.cover-mark')?.textContent).toContain('8월 8일');
    expect(container.querySelector('.cover-hint')?.textContent).toContain('위로 넘겨서');
  });

  it('puts the quote after the hint so the fold order stays date -> hint -> quote', () => {
    const { container } = renderCover({ ...COVER, quote: QUOTE });

    const body = container.querySelector('.card-body');
    const children = Array.from(body?.children ?? []).map((el) => el.className);
    expect(children.indexOf('cover-quote')).toBeGreaterThan(children.indexOf('cover-hint'));
  });
});
