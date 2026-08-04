import type { Trending, TrendingItem } from '../content';

interface TrendingSlideProps {
  trending: Trending;
  isActive: boolean;
  onOpenTopic: (item: TrendingItem) => void;
}

/** 24시간 트렌딩 토픽 TOP 10. 카드 한 장에 10행이 스크롤 없이 들어가야 하므로
 *  .card-body를 카드 전체 높이로 늘리고(feed.css) 목록을 flex로 균등 분할한다 —
 *  기기별로 카드 높이가 달라져도(뷰포트 91vh) 항상 딱 맞는다. */
export function TrendingSlide({ trending, isActive, onOpenTopic }: TrendingSlideProps) {
  return (
    <div className={'slide' + (isActive ? ' is-active' : '')} role="group">
      <div className="card is-trending">
        <div className="card-body">
          <div className="trending-head">
            <span className="badge">{trending.eyebrow}</span>
            <h2 className="trending-title">{trending.title}</h2>
            {trending.note && <p className="trending-note">{trending.note}</p>}
          </div>

          <ol className="trending-list">
            {trending.items.map((item) => {
              const canExpand = (item.links?.length ?? 0) > 0;
              const body = (
                <>
                  <span className="trending-rank">{item.rank}</span>
                  <div className="trending-main">
                    <div className="trending-topic-row">
                      <span className="trending-topic">{item.topic}</span>
                      <span className="trending-figures">
                        {item.mentions}건 · {item.sources}개 매체
                      </span>
                      {canExpand && <span className="trending-expand">펼치기</span>}
                    </div>
                    <div className="trending-bar-track">
                      <div className="trending-bar-fill" style={{ width: `${item.heat}%` }} />
                    </div>
                  </div>
                </>
              );
              return (
                <li key={item.rank} className={'trending-row' + (item.rank <= 3 ? ' is-top' : '')}>
                  {canExpand ? (
                    <button
                      type="button"
                      className="trending-open"
                      aria-label={`${item.topic} 원문 목록 펼치기`}
                      onClick={() => onOpenTopic(item)}
                    >
                      {body}
                    </button>
                  ) : (
                    body
                  )}
                </li>
              );
            })}
          </ol>
        </div>
      </div>
    </div>
  );
}
