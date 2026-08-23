interface FeedNavProps {
  onPrev: () => void;
  onNext: () => void;
  /** 첫 슬라이드면 위로 갈 곳이 없다. */
  atStart: boolean;
  /** 마지막이면 아래로 갈 곳이 없다(피드가 더 불러올 게 남았으면 마지막이 아니다). */
  atEnd: boolean;
}

/** 위/아래 이동 버튼.
 *
 *  스와이프를 모르는 독자가 있다는 걸 제보로 알았다(2026-08-23: 표지에서 스와이프가
 *  죽었을 때 "로딩만 되고 나오질 않네요"라는 반응이 나왔다). 스와이프 자체는 고쳤지만,
 *  넘기는 방법이 눈에 보이지 않으면 같은 오해가 또 난다. 눌러서도 넘길 수 있게 둔다.
 *
 *  PC에서는 카드(max 430px) 옆 여백에 세워 카드를 전혀 가리지 않고, 모바일에서는
 *  카드가 화면을 꽉 채우므로 엄지가 닿는 우하단에 반투명으로 얹는다(feed-nav.css).
 *
 *  끝에 닿으면 감추지 않고 비활성으로 남긴다 — 버튼이 사라지면 자리가 밀려서
 *  다음 클릭이 엉뚱한 곳을 누른다.
 */
export function FeedNav({ onPrev, onNext, atStart, atEnd }: FeedNavProps) {
  return (
    <div className="feed-nav">
      <button
        type="button"
        className="feed-nav-btn"
        onClick={onPrev}
        disabled={atStart}
        aria-label="이전 카드"
      >
        <Chevron up />
      </button>
      <button
        type="button"
        className="feed-nav-btn"
        onClick={onNext}
        disabled={atEnd}
        aria-label="다음 카드"
      >
        <Chevron />
      </button>
    </div>
  );
}

/** 아이콘은 인라인 SVG로 둔다 — 이모지 금지 규칙이 있고, 이 둘 때문에
 *  아이콘 라이브러리를 물리면 번들만 늘어난다. */
function Chevron({ up = false }: { up?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
      <path
        d={up ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'}
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
