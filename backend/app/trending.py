"""Rank the last 24h's candidate topics by how "hot" they were — not by raw mention count.

Pure computation only, no network calls. `collect_daily.py` feeds this the same
filtered news/video candidate lists it already builds and writes the top 15 into
`trending_candidates` for a human (or Claude) to curate down to 10 with labels.

왜 "언급 수"가 아니라 "핫함"인가: 매체 하나가 같은 사건을 5번 우려먹은 것과, 매체
5곳이 각자 한 번씩 동시에 다룬 것은 언급 수로는 똑같이 5지만 화제성은 전혀 다르다.
그래서 점수 공식은 매체 다양성에 지수를 주고(diversity ** 1.5), 반복 언급의 효과는
log로 눌러 죽인다(volume). 자세한 배점 근거는 rank_topics 본문 주석 참고.
"""

import datetime
import math
import re
from collections.abc import Collection
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

# 거의 모든 기사/영상에 붙어 토픽으로서 변별력이 없는 태그. 모듈 상수라 필요하면
# 여기만 고치면 된다.
STOPWORDS: set[str] = {
    "비트코인",
    "btc",
    #  영문 태그도 막는다. my-news 의 auto_interested 소스는 분류기를 건너뛰어
    #  fetcher 의 영문 태그(["bitcoin","crypto"])가 그대로 남는데, 이 둘이 빠져
    #  있으면 "bitcoin" 이 매체 18곳짜리 트렌딩 1위 토픽이 된다(2026-09-10 실측).
    "bitcoin",
    "crypto",
    "암호화폐",
    "가상자산",
    "코인",
    "크립토",
    "시장",
    "가격",
    "투자",
    # 아래는 "그날의 사건"이 아니라 매일 붙는 배경 서술이다. 특히 유튜브는 대부분이
    # 일일 시황 코멘터리라, 이걸 토픽으로 세면 채널 수가 그대로 매체 다양성으로
    # 둔갑해 실제 사건들을 전부 눌러버린다(2026-08-05: 25건 19매체로 1위 차지).
    "가격분석",
    "가격전망",
    "시장분석",
    "변동성",
    "반등",
    "시황",
}

# 표기만 다른 같은 토픽을 하나로 합친다. 키는 소문자 + 공백 제거로 정규화해서
# 조회하므로 "Fed"/"fed"/"FED"가 전부 같은 키로 들어온다.
SYNONYMS: dict[str, str] = {
    "fed": "연준",
    "연준": "연준",
    "fomc": "연준",
    "연방준비제도": "연준",
    "etf": "ETF",
    "coldcard": "콜드카드",
    "콜드카드": "콜드카드",
    "clarity": "클래리티 법안",
    "클래리티": "클래리티 법안",
    "클래리티법안": "클래리티 법안",
    "sec": "SEC",
    "microstrategy": "스트래티지",
    "마이크로스트래티지": "스트래티지",
    "스트래티지": "스트래티지",
}

# 후보 15개를 넘겨 Claude가 겹치는 것끼리 묶어 10개로 정리할 여유를 준다.
TOP_N = 15

# 영상 제목을 대조할 때 기준으로 삼을 토픽 수. 뉴스·X 태그를 다 모으면 토픽이
# 679개까지 늘어나고(2026-09-10 실측) 거기엔 "금"·"미팅" 같은 한 번 스친 말이
# 섞여 있어서, 전체를 기준으로 대조하면 영상 하나가 토픽 7개에 걸린다. 어차피
# 결과는 상위 TOP_N 이므로 그 언저리까지만 기준으로 둔다 — 영상이 붙어서 15위
# 안으로 올라올 토픽을 담을 만큼은 넉넉해야 해서 TOP_N 보다 크게 잡는다.
TITLE_MATCH_POOL = 40

# 제목 대조에 쓸 토픽의 최소 길이. 한 글자 토픽은 다른 말 안에 그대로 들어간다
# ("금"이 "금리"에, "달"이 "달러"에). ASCII 는 단어 경계로 맞추므로 이 제한이
# 필요 없지만, 한글은 부분 문자열이라 걸러야 한다.
MIN_TITLE_MATCH_LEN = 2

_HASHTAG_RE = re.compile(r"#(\S+)")


class ArticleRef(TypedDict):
    """트렌딩 항목을 펼쳤을 때 보여줄 기사/영상 하나."""

    title: str
    url: str
    source: str


class TopicSignal(TypedDict):
    """rank_topics의 출력 원소. topic 하나에 대한 집계 결과 + 사람이 라벨을 붙일 때 쓸 근거."""

    topic: str
    score: float
    heat: int
    mentions: int
    sources: int
    #  X 언급 수. mentions 와 따로 두는 이유는 `rank_topics` 본문 주석 참고 —
    #  카드에 찍히는 "N건 N매체"는 뉴스·영상 기준이어야 하고, X 반응은 순위를
    #  움직이는 근거로만 쓴다. 카드 10장을 고를 때 "뉴스는 조용했는데 X 가
    #  시끄러웠던 토픽"을 알아보라고 draft 에 실어 둔다.
    tweet_mentions: int
    source_names: list[str]
    example_titles: list[str]
    articles: list[ArticleRef]


# 펼침 목록에 담을 기사 수. 시트 한 화면에 들어가고, 같은 사건을 다룬 매체가
# 몇 곳인지 눈으로 확인되는 정도면 충분하다.
MAX_ARTICLES = 6


def _normalize_tag(raw: str) -> str | None:
    """`#태그` → 정규화된 토픽명. 불용어면 None."""
    text = re.sub(r"\s+", " ", raw.lstrip("#").strip())
    if not text:
        return None
    key = text.lower().replace(" ", "")
    if key in STOPWORDS:
        return None
    return SYNONYMS.get(key, text)


def _extract_hashtags(text: str) -> list[str]:
    return _HASHTAG_RE.findall(text or "")


def _topic_aliases(topic: str) -> set[str]:
    """토픽 하나를 제목에서 찾을 때 쓸 표기들. 정규 이름 + SYNONYMS 의 역방향.

    "연준" 토픽은 제목에 "FOMC"나 "Fed"로 적히는 쪽이 오히려 흔하다. 정규 이름만
    대조하면 그런 영상이 통째로 빠진다.
    """
    aliases = {topic}
    for raw, canonical in SYNONYMS.items():
        if canonical == topic:
            aliases.add(raw)
    return aliases


def _mentions_term(text: str, term: str) -> bool:
    """text 안에 term 이 등장하는가.

    ASCII 는 단어 경계로, 한글은 부분 문자열로 맞춘다 — `collect_daily._term_hits`
    와 같은 규칙이다. 이 구분이 없으면 "AI"가 "Ukraine"이나 "again"에 걸린다
    (2026-09-08 영상 코퍼스 실측).
    """
    low = text.lower()
    t = term.lower()
    if t.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", low) is not None
    return t in low


def _title_topics(title: str, known_topics: Collection[str]) -> set[str]:
    """영상 제목에서 이미 집계된 토픽을 찾는다. **제목만** 본다.

    요약까지 보면 매칭률은 3/13 에서 11/13 으로 오르지만 오탐이 심하다 —
    2026-09-08 실측에서 "HUGE! BIS USES XRP LEDGER" 한 건이 스테이블코인·ETF·
    블록체인·규제·보안·은행 6개 토픽에 동시에 걸렸다. 유튜브는 조회수가 자릿수로
    벌어져서, 그런 영상 하나가 여러 토픽의 view_sum 을 동시에 부풀리면 순위가
    통째로 왜곡된다. `collect_daily._title_hits` 가 policy 등급을 제목만으로
    판정하는 것과 같은 이유다.
    """
    if not title:
        return set()
    return {
        topic
        for topic in known_topics
        if len(topic) >= MIN_TITLE_MATCH_LEN
        and any(_mentions_term(title, alias) for alias in _topic_aliases(topic))
    }


def _item_topics(raw_tags: list[str]) -> set[str]:
    topics: set[str] = set()
    for raw in raw_tags:
        normalized = _normalize_tag(raw)
        if normalized:
            topics.add(normalized)
    return topics


def _parse_kst(value: str | None) -> datetime.datetime | None:
    """news/video의 published_at을 파싱한다.

    tz 정보가 없는 문자열(뉴스 후보가 대개 이 형태)은 KST로 간주한다 — 수집기
    원본이 한국 매체라 이미 KST 로컬 시각이다. tz가 붙은 문자열(유튜브의
    `...Z` 등)은 그대로 존중한다.
    """
    if not value:
        return None
    dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt


def _recency_multiplier(latest: datetime.datetime | None, now: datetime.datetime) -> float:
    if latest is None:
        return 1.0
    hours = (now - latest).total_seconds() / 3600
    if hours <= 6:
        return 1.3
    if hours <= 12:
        return 1.15
    return 1.0


class _Accumulator:
    """topic → 원시 집계치. rank_topics 안에서만 쓰는 내부 누산기."""

    def __init__(self) -> None:
        self.sources: dict[str, set[str]] = {}
        self.mentions: dict[str, int] = {}
        self.latest: dict[str, datetime.datetime] = {}
        self.view_sum: dict[str, int] = {}
        self.examples: dict[str, list[ArticleRef]] = {}
        #  X 는 sources/mentions 와 분리해서 센다(add_tweet 참고).
        self.tweet_mentions: dict[str, int] = {}

    def add_tweet(self, topic: str, published: datetime.datetime | None) -> None:
        """X 언급 하나를 센다. sources/mentions/examples 는 건드리지 않는다.

        계정을 매체와 같은 층에 넣으면 diversity(매체 수 ** 1.5)가 X 에 지배된다 —
        24시간 트윗이 683건 313계정인데 뉴스는 168건 22매체라(2026-09-10 실측),
        합치는 순간 뉴스 기반 순위 구조가 통째로 뒤집힌다. 최신성에는 기여하게
        둔다 — 지금 막 터진 토픽이라는 신호는 X 가 가장 빠르다.
        """
        self.tweet_mentions[topic] = self.tweet_mentions.get(topic, 0) + 1
        if published is not None:
            current = self.latest.get(topic)
            if current is None or published > current:
                self.latest[topic] = published

    def add(
        self,
        topic: str,
        source_name: str | None,
        published: datetime.datetime | None,
        title: str | None,
        views: int = 0,
        url: str | None = None,
    ) -> None:
        self.sources.setdefault(topic, set())
        if source_name:
            self.sources[topic].add(source_name)
        self.mentions[topic] = self.mentions.get(topic, 0) + 1
        if published is not None:
            current = self.latest.get(topic)
            if current is None or published > current:
                self.latest[topic] = published
        if views:
            self.view_sum[topic] = self.view_sum.get(topic, 0) + views
        if title:
            bucket = self.examples.setdefault(topic, [])
            # 같은 기사가 두 태그로 두 번 들어오면 목록에 중복으로 뜬다. 제목으로 막는다.
            if len(bucket) < MAX_ARTICLES and all(a["title"] != title for a in bucket):
                bucket.append({"title": title, "url": url or "", "source": source_name or ""})


def _score_all(acc: "_Accumulator", now: datetime.datetime) -> list[dict[str, Any]]:
    """누산기 상태를 점수순 목록으로 만든다. 점수 공식의 유일한 자리다.

    `rank_topics` 가 두 번 부른다 — 한 번은 뉴스·X 만으로 영상 제목을 대조할
    기준 토픽을 추리려고, 다시 한 번은 영상까지 넣은 최종 순위를 내려고.
    """
    scored: list[dict[str, Any]] = []
    for topic, mentions in acc.mentions.items():
        diversity = len(acc.sources[topic]) ** 1.5
        volume = math.log2(1 + mentions)
        recency = _recency_multiplier(acc.latest.get(topic), now)
        youtube = 1 + math.log10(1 + acc.view_sum.get(topic, 0)) / 10
        tweet_mentions = acc.tweet_mentions.get(topic, 0)
        x_buzz = 1 + math.log10(1 + tweet_mentions) / 10
        score = diversity * volume * recency * youtube * x_buzz
        scored.append(
            {
                "topic": topic,
                "score": score,
                "mentions": mentions,
                "sources": len(acc.sources[topic]),
                "tweet_mentions": tweet_mentions,
                "source_names": sorted(acc.sources[topic]),
                "examples": acc.examples.get(topic, []),
            }
        )
    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored


def rank_topics(
    news: list[dict[str, Any]],
    videos: list[dict[str, Any]],
    now: datetime.datetime,
    tweets: list[dict[str, Any]] | None = None,
) -> list[TopicSignal]:
    """뉴스/영상/X 후보에서 토픽을 뽑아 "얼마나 핫했는지" 점수순으로 상위 15개를 낸다.

    점수 공식과 근거:
        diversity = (서로 다른 매체 수) ** 1.5
            매체 다양성에 지수를 준다 — 매체 5곳이 동시에 다뤘다는 건 한 매체가
            같은 사건을 5번 우려먹은 것보다 훨씬 강한 "진짜 화제" 신호다. 지수를
            줘서 매체 수가 늘수록 가중이 가속되게 한다(1곳→1, 2곳→2.8, 5곳→11.2).
        volume = log2(1 + 언급 수)
            반대로 언급 수 자체는 log로 눌러 죽인다. 그렇지 않으면 매체 하나가
            글을 열 번 쏟아내는 것만으로 diversity 부재를 물량으로 뒤집어버린다.
        recency = 최근성 가중 (6h 이내 1.3 / 12h 이내 1.15 / 그 외 1.0)
            오래전에 반짝했다 가라앉은 토픽보다 지금 막 터진 토픽이 더 핫하다.
        youtube = 1 + log10(1 + 조회수 합) / 10
            유튜브 반응도 신호로 더하되, 조회수는 자릿수 단위로 벌어지므로
            log10을 쓰고 나눗셈으로 완만하게 만든다 — 기사 위주 토픽이 조회수
            보정만으로 순위가 뒤집히지 않게 하는 정도로만 가중한다.
            영상이 어느 토픽에 속하는지는 태그와 **제목 대조**로 정한다
            (`_title_topics`). 태그만 보던 동안에는 my-youtube 가 모든 영상에
            topic="비트코인" 하나만 붙이고 그 말이 STOPWORDS 라, 이 배수가
            한 번도 1.0 을 벗어난 적이 없었다(2026-09-07~09 실측).
        x_buzz = 1 + log10(1 + X 언급 수) / 10
            X 반응도 같은 방식으로 얹는다. 계정을 sources 에 합치지 않는 이유는
            `_Accumulator.add_tweet` 주석에 있다 — 계정 수가 매체 수를 압도해
            diversity 를 통째로 삼킨다. 배수로 넣으면 뉴스 기반 순위를 유지한 채
            "X 에서도 시끄러웠다"만 순위에 얹힌다.
        score = diversity * volume * recency * youtube * x_buzz

    heat은 최고 점수를 100으로 정규화한 정수다.

    tweets 를 안 넘기면(기본값) X 배수가 전부 1.0 이라 예전과 같은 순위가 나온다.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)

    acc = _Accumulator()

    for item in news:
        topics = _item_topics(item.get("tags") or [])
        published = _parse_kst(item.get("published_at"))
        for topic in topics:
            acc.add(
                topic,
                item.get("source_ref"),
                published,
                item.get("title"),
                url=item.get("url"),
            )

    # X 를 영상보다 먼저 본다 — 영상은 아래에서 "지금까지 모인 토픽"으로 제목을
    # 대조하므로, 뉴스와 X 의 토픽이 다 모인 뒤라야 붙을 자리가 생긴다.
    for item in tweets or []:
        topics = _item_topics(item.get("tags") or [])
        published = _parse_kst(item.get("time") or item.get("crawled_at"))
        for topic in topics:
            acc.add_tweet(topic, published)

    # 영상 제목을 대조할 기준 토픽. 뉴스·X 태그를 다 모으면 한 번 스친 말까지
    # 토픽이 되므로(2026-09-10 실측 679개) 상위 TITLE_MATCH_POOL 개로 좁힌다.
    # 이 시점의 acc 에는 뉴스와 X 만 들어 있어 영상이 자기 순위를 스스로 밀어
    # 올리는 일이 없다.
    #
    # 점수 상위만으로는 부족하다. 점수는 mentions(뉴스·영상) 기반이라 X 에서만
    # 나온 토픽은 volume 이 0 이라 아예 순위에 없다. "뉴스는 안 다뤘는데 X 와
    # 유튜브가 동시에 다룬 화제"는 놓치면 안 되는 신호라, X 언급 상위도 같이
    # 기준에 넣는다.
    by_score = [entry["topic"] for entry in _score_all(acc, now)[:TITLE_MATCH_POOL]]
    by_buzz = sorted(acc.tweet_mentions, key=lambda t: -acc.tweet_mentions[t])
    known_topics = set(by_score) | set(by_buzz[:TITLE_MATCH_POOL])

    for item in videos:
        raw_tags = [item.get("topic") or "", *_extract_hashtags(item.get("title") or "")]
        # 태그 경로와 제목 대조 경로를 합친다. 태그 경로를 남기는 이유는 my-youtube 가
        # 나중에 태그를 제대로 붙이기 시작하면 그쪽이 저절로 살아나야 해서다.
        # 지금은 모든 영상에 topic 이 "비트코인" 하나뿐이고 그 말이 STOPWORDS 라
        # 태그 경로만으로는 영상이 한 건도 집계에 들어오지 못한다(2026-09-07~09 실측:
        # 상위 15개 토픽의 매체 목록에 유튜브 채널 0개). 그래서 제목 대조를 더한다.
        topics = _item_topics(raw_tags) | _title_topics(item.get("title") or "", known_topics)
        published = _parse_kst(item.get("published_at"))
        # my-youtube 응답에 url이 없는 항목이 있어 id로 복원한다.
        video_url = item.get("url")
        if not video_url and item.get("id"):
            video_url = f"https://www.youtube.com/watch?v={item['id']}"
        for topic in topics:
            acc.add(
                topic,
                item.get("channel_title"),
                published,
                item.get("title"),
                views=item.get("view_count") or 0,
                url=video_url,
            )

    if not acc.mentions:
        return []

    scored = _score_all(acc, now)
    top = scored[:TOP_N]
    max_score = top[0]["score"] if top else 0.0

    result: list[TopicSignal] = []
    for entry in top:
        heat = round(100 * entry["score"] / max_score) if max_score > 0 else 0
        examples = entry["examples"]
        result.append(
            {
                "topic": entry["topic"],
                "score": round(entry["score"], 4),
                "heat": heat,
                "mentions": entry["mentions"],
                "sources": entry["sources"],
                "tweet_mentions": entry["tweet_mentions"],
                "source_names": entry["source_names"],
                "example_titles": [a["title"] for a in examples[:3]],
                # url이 없는 항목은 뺀다 — 펼쳤을 때 눌리지 않는 줄이 남으면 고장으로 보인다.
                "articles": [a for a in examples if a["url"]],
            }
        )
    return result
