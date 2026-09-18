/** 카드 한 장을 링크로 공유한다.
 *
 *  모바일에서는 운영체제 공유 시트를 띄우고(`navigator.share`), 그게 없는 데스크톱
 *  브라우저에서는 주소를 클립보드에 복사한다. 둘 다 못 쓰는 환경이면 실패를 알린다 —
 *  아무 일도 일어나지 않은 채 조용히 끝나면 사용자는 버튼이 고장난 줄 안다.
 */

export type ShareOutcome =
  | { kind: 'shared' }
  | { kind: 'copied' }
  | { kind: 'cancelled' }
  | { kind: 'failed'; message: string };

export interface ShareCardInput {
  date: string;
  /** 에디션 안의 슬라이드 위치. `card.num` 이 아니라 `/d/:date/:index` 의 index 다. */
  index: number;
  title: string;
  /** 테스트에서 주소를 고정하려고 둔다. 실제로는 현재 창의 origin 을 쓴다. */
  origin?: string;
}

export function cardShareUrl({ date, index, origin }: ShareCardInput): string {
  const base = origin ?? window.location.origin;
  // 서브패스에 올라간 사이트도 같은 코드로 맞는 주소를 만든다. 이 카드뉴스는 도메인
  // 루트에 있어 BASE_URL 이 "/" 지만, 자매 사이트는 "/ai/" 밑에서 서빙한다.
  const prefix = import.meta.env.BASE_URL.replace(/\/$/, '');
  return `${base}${prefix}/d/${date}/${index}`;
}

export async function shareCard(input: ShareCardInput): Promise<ShareOutcome> {
  const url = cardShareUrl(input);

  if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
    try {
      await navigator.share({ title: input.title, url });
      return { kind: 'shared' };
    } catch (err) {
      // 사용자가 공유 시트를 닫은 것은 실패가 아니다. 메시지를 띄우면 오히려 성가시다.
      if (err instanceof Error && err.name === 'AbortError') return { kind: 'cancelled' };
      // 공유 시트를 못 연 경우는 아래 클립보드로 넘어간다.
    }
  }

  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(url);
      return { kind: 'copied' };
    } catch {
      return { kind: 'failed', message: '링크를 복사하지 못했습니다.' };
    }
  }

  return { kind: 'failed', message: '이 브라우저에서는 공유를 지원하지 않습니다.' };
}
