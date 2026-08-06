import { speakerShortName } from '../content';
import { bundledPortraits } from '../media';

interface SpeakerAvatarProps {
  author: string;
  portrait?: string | null;
  /** 테스트에서 갈아끼우기 위한 구멍. 기본값은 번들된 초상 전부. */
  portraits?: Record<string, string>;
}

/** 표지 인용구를 말한 사람.
 *
 *  사진은 **퍼블릭 도메인인 것만** 저장소에 둔다(CONTENT_CONTRACT.md 4장). 공개
 *  사이트라 CC BY-SA 사진은 저작자 표기 줄이 인용구보다 길어져 카드가 지저분해진다.
 *  그래서 사진이 있는 인물이 오히려 소수이고, 나머지는 이름을 조판해 그 자리를 채운다
 *  — CardArtFallback 이 이미지 없는 카드를 다루는 방식과 같은 태도다.
 *
 *  둘 다 aria-hidden 이다. 바로 아래 figcaption 에 저자 이름이 글자로 있어서,
 *  읽어주면 같은 이름이 두 번 나온다. */
export function SpeakerAvatar({
  author,
  portrait,
  portraits = bundledPortraits,
}: SpeakerAvatarProps) {
  const src = portrait ? portraits[portrait] : undefined;

  if (src) {
    return (
      <img
        className="speaker-avatar"
        src={src}
        alt=""
        aria-hidden="true"
        loading="lazy"
        decoding="async"
      />
    );
  }

  return (
    <span className="speaker-avatar is-type" aria-hidden="true">
      {speakerShortName(author)}
    </span>
  );
}
