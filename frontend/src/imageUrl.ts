/** 카드 이미지의 실제 src를 고른다.
 *
 *  발행분은 뉴스사 CDN의 절대 URL을 담고 있는데(CONTENT_CONTRACT.md 4장), 원본은
 *  실측 평균 380KB다. 카드의 이미지 영역은 뷰포트 폭 그대로라 모바일에서 400px가
 *  채 안 되므로 백엔드 프록시(/api/img)로 줄여 받는다. 로컬 시드 fixture가 쓰는
 *  stem('fed-macro')은 번들 asset이라 그대로 쓴다.
 */

const WIDTH_DEFAULT = 800;
const WIDTH_SAVE_DATA = 480;

interface SaveDataConnection {
  saveData?: boolean;
}

/** 데이터 절약 모드면 절반 폭으로 받는다. 백엔드가 허용 폭을 이 둘로 고정한다. */
export function preferredImageWidth(): number {
  if (typeof navigator === 'undefined') return WIDTH_DEFAULT;
  const connection = (navigator as Navigator & { connection?: SaveDataConnection }).connection;
  return connection?.saveData ? WIDTH_SAVE_DATA : WIDTH_DEFAULT;
}

export function isRemoteImage(image: string | null | undefined): boolean {
  return typeof image === 'string' && /^https?:\/\//.test(image);
}

export function cardImageSrc(
  date: string,
  num: number,
  image: string | null | undefined,
  bundled: Record<string, string>,
): string | undefined {
  if (!image) return undefined;
  if (isRemoteImage(image)) return `/api/img/${date}/${num}?w=${preferredImageWidth()}`;
  return bundled[image];
}
