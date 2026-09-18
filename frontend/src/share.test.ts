import { afterEach, describe, expect, it, vi } from 'vitest';
import { cardShareUrl, shareCard } from './share';

const INPUT = {
  date: '2026-09-18',
  index: 3,
  title: '세 번째 카드',
  origin: 'https://example.test',
};

/** 이 사이트가 어느 경로에 올라가 있든 같은 기대값을 만든다.
 *  도메인 루트면 빈 문자열, 서브패스(자매 사이트의 "/ai/")면 그 접두사가 붙는다. */
const EXPECTED_URL = `https://example.test${import.meta.env.BASE_URL.replace(/\/$/, '')}/d/2026-09-18/3`;

function stubNavigator(patch: Record<string, unknown>) {
  for (const [key, value] of Object.entries(patch)) {
    Object.defineProperty(navigator, key, { value, configurable: true, writable: true });
  }
}

afterEach(() => {
  // jsdom 의 navigator 는 share 도 clipboard 도 없다. 심은 것만 지운다.
  for (const key of ['share', 'clipboard']) {
    if (key in navigator) delete (navigator as unknown as Record<string, unknown>)[key];
  }
  vi.restoreAllMocks();
});

describe('cardShareUrl', () => {
  it('슬라이드 위치를 주소에 담는다', () => {
    // index 는 card.num 이 아니라 에디션 안의 슬라이드 위치다.
    expect(cardShareUrl(INPUT)).toBe(EXPECTED_URL);
  });
});

describe('shareCard', () => {
  it('네이티브 공유 시트가 있으면 그것을 쓴다', async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    stubNavigator({ share });

    await expect(shareCard(INPUT)).resolves.toEqual({ kind: 'shared' });
    expect(share).toHaveBeenCalledWith({ title: '세 번째 카드', url: EXPECTED_URL });
  });

  it('사용자가 공유 시트를 닫으면 실패로 보지 않는다', async () => {
    // 취소에 오류 메시지를 띄우면 성가시기만 하다.
    const abort = new Error('closed');
    abort.name = 'AbortError';
    stubNavigator({ share: vi.fn().mockRejectedValue(abort) });

    await expect(shareCard(INPUT)).resolves.toEqual({ kind: 'cancelled' });
  });

  it('공유 시트가 없으면 클립보드로 복사한다', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubNavigator({ clipboard: { writeText } });

    await expect(shareCard(INPUT)).resolves.toEqual({ kind: 'copied' });
    expect(writeText).toHaveBeenCalledWith(EXPECTED_URL);
  });

  it('공유 시트가 열리지 않으면 클립보드로 넘어간다', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubNavigator({
      share: vi.fn().mockRejectedValue(new Error('not allowed')),
      clipboard: { writeText },
    });

    await expect(shareCard(INPUT)).resolves.toEqual({ kind: 'copied' });
  });

  it('클립보드 복사가 막히면 사유를 알린다', async () => {
    stubNavigator({ clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } });

    await expect(shareCard(INPUT)).resolves.toEqual({
      kind: 'failed',
      message: '링크를 복사하지 못했습니다.',
    });
  });

  it('둘 다 없으면 조용히 끝내지 않고 알린다', async () => {
    // 아무 일도 안 일어난 채 끝나면 사용자는 버튼이 고장난 줄 안다.
    await expect(shareCard(INPUT)).resolves.toEqual({
      kind: 'failed',
      message: '이 브라우저에서는 공유를 지원하지 않습니다.',
    });
  });
});
