interface ErrorSlideProps {
  date: string;
  message: string;
  isActive: boolean;
}

/** 한 날짜가 실패해도 피드 전체를 죽이지 않는다 — 그 자리에만 이 슬라이드가 선다. */
export function ErrorSlide({ date, message, isActive }: ErrorSlideProps) {
  return (
    <div className={'slide' + (isActive ? ' is-active' : '')} role="group">
      <div className="card is-closing">
        <div className="card-body">
          <span className="badge">{date}</span>
          <p className="body-text">{message}</p>
          <p className="disclaimer">계속 올리면 그 이전 날짜로 넘어갑니다.</p>
        </div>
      </div>
    </div>
  );
}
