import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DetailSheet } from './DetailSheet';
import { FeedChrome } from './FeedChrome';
import { CardSlide } from './slides/CardSlide';
import { ClosingSlide } from './slides/ClosingSlide';
import { CoverSlide } from './slides/CoverSlide';
import { ErrorSlide } from './slides/ErrorSlide';
import { TrendingSlide } from './slides/TrendingSlide';
import { useEditionQueue } from './useEditionQueue';
import { useThemeVars, type Theme } from './useThemeVars';
import { useVerticalFeed } from './useVerticalFeed';
import { bundledMedia } from './media';
import type { Card, EditionContent } from './content';
import './feed.css';

/** 현재 슬라이드에서 이만큼 떨어진 카드까지만 이미지를 실제로 받는다.
 *  loading="lazy"는 스냅 스크롤로 빠르게 지나가면 근처를 전부 받아버린다. */
const IMAGE_WINDOW = 2;
/** 끝에서 이만큼 남으면 다음 날짜를 붙인다 — 클로징에서 빈 화면이 뜨지 않도록. */
const APPEND_AHEAD = 2;

const EMPTY_THEME: Theme = {};

type SlideKind = 'cover' | 'card' | 'trending' | 'closing' | 'error';

interface FeedSlide {
  key: string;
  date: string;
  editionIndex: number;
  /** 그 에디션 안에서의 위치. 0 = 표지. */
  localIndex: number;
  localTotal: number;
  kind: SlideKind;
  content: EditionContent | null;
  card: Card | null;
  error: string | null;
}

function buildSlides(
  entries: { date: string; content: EditionContent | null; error: string | null }[],
): FeedSlide[] {
  return entries.flatMap((entry, editionIndex): FeedSlide[] => {
    if (!entry.content) {
      return [
        {
          key: `${entry.date}-error`,
          date: entry.date,
          editionIndex,
          localIndex: 0,
          localTotal: 1,
          kind: 'error',
          content: null,
          card: null,
          error: entry.error ?? '이 날짜를 불러오지 못했습니다.',
        },
      ];
    }

    const cards = entry.content.cards;
    // 트렌딩 블록이 있으면 클로징 앞에 한 장 더 낀다 — 없는 과거 9편은 그대로 12장.
    const trending = entry.content.trending;
    const localTotal = cards.length + 2 + (trending ? 1 : 0);
    const shared = {
      date: entry.date,
      editionIndex,
      localTotal,
      content: entry.content,
      error: null,
    };

    const slides: FeedSlide[] = [
      { ...shared, key: `${entry.date}-cover`, localIndex: 0, kind: 'cover', card: null },
      ...cards.map((card, i) => ({
        ...shared,
        key: `${entry.date}-${card.num}`,
        localIndex: i + 1,
        kind: 'card' as const,
        card,
      })),
    ];
    if (trending) {
      slides.push({
        ...shared,
        key: `${entry.date}-trending`,
        localIndex: cards.length + 1,
        kind: 'trending',
        card: null,
      });
    }
    slides.push({
      ...shared,
      key: `${entry.date}-closing`,
      localIndex: localTotal - 1,
      kind: 'closing',
      card: null,
    });
    return slides;
  });
}

interface ShortsFeedProps {
  startDate: string;
  /** 딥링크로 들어온 카드 위치(/d/:date/:index). */
  startIndex: number;
}

/** 최신 날짜에서 과거로 끝없이 이어지는 세로 스냅 피드.
 *
 *  날짜 경계에는 별도 구분 카드를 두지 않는다. 각 에디션의 표지가 이미 날짜를
 *  크게 보여주므로, 클로징 다음에 바로 다음 날 표지가 오면 그게 구분선이다.
 */
export function ShortsFeed({ startDate, startIndex }: ShortsFeedProps) {
  const { entries, loadMore, hasMore, cappedByLimit, listError, publishedDates } =
    useEditionQueue(startDate);
  const [sheetCard, setSheetCard] = useState<Card | null>(null);
  const navigate = useNavigate();
  const jumpedToStart = useRef(false);

  const slides = useMemo(() => buildSlides(entries), [entries]);
  const { current, trackRef, goTo } = useVerticalFeed(slides.length, sheetCard !== null);

  const currentSlide = slides[current];
  const theme = currentSlide?.content?.theme ?? EMPTY_THEME;
  useThemeVars(theme);

  /** 현재 에디션의 첫 슬라이드가 전체에서 몇 번째인지 — 진행바가 이 오프셋을 쓴다. */
  const editionOffset = useMemo(() => {
    if (!currentSlide) return 0;
    return slides.findIndex((s) => s.editionIndex === currentSlide.editionIndex);
  }, [slides, currentSlide]);

  useEffect(() => {
    if (hasMore && current >= slides.length - 1 - APPEND_AHEAD) loadMore();
  }, [current, slides.length, hasMore, loadMore]);

  // 딥링크 위치로 한 번만 점프한다. 이후 append로 slides가 늘어도 다시 뛰지 않는다.
  useEffect(() => {
    if (jumpedToStart.current || slides.length === 0) return;
    jumpedToStart.current = true;
    if (startIndex > 0) goTo(Math.min(startIndex, slides.length - 1));
  }, [slides.length, startIndex, goTo]);

  // 스크롤로 주소를 갱신하지 않는다. `/`에서 시작한 사람이 스크롤만 해도 주소가
  // `/d/{그날}`로 바뀌면, 거기서 북마크한 링크가 그 날짜에 고정돼 다음 날 열어도
  // 지난 편을 본다. 주소는 사용자가 의도적으로 이동할 때만(캘린더·공유 링크) 바뀐다.

  const selectDate = useCallback(
    (picked: string) => {
      // 이미 피드에 실려 있으면 네트워크 없이 그 자리로 스크롤한다.
      const offset = slides.findIndex((s) => s.date === picked);
      if (offset >= 0) goTo(offset);
      else navigate(`/d/${picked}`);
    },
    [slides, goTo, navigate],
  );

  if (listError && entries.length === 0) return <div className="status-screen">{listError}</div>;
  if (slides.length === 0) return <div className="status-screen">불러오는 중…</div>;

  return (
    <div className="feed">
      <FeedChrome
        brand={currentSlide?.content?.brand ?? '데일리 비트코인'}
        date={currentSlide?.date ?? startDate}
        localIndex={currentSlide?.localIndex ?? 0}
        localTotal={currentSlide?.localTotal ?? 1}
        publishedDates={publishedDates}
        onGoToLocal={(i) => goTo(editionOffset + i)}
        onSelectDate={selectDate}
      />

      <div className={'feed-track' + (sheetCard ? ' is-locked' : '')} ref={trackRef}>
        {slides.map((slide, index) => {
          const isActive = index === current;
          const shouldLoadImage = Math.abs(index - current) <= IMAGE_WINDOW;

          if (slide.kind === 'error') {
            return (
              <ErrorSlide
                key={slide.key}
                date={slide.date}
                message={slide.error ?? ''}
                isActive={isActive}
              />
            );
          }
          if (slide.kind === 'cover') {
            return (
              <CoverSlide
                key={slide.key}
                cover={slide.content!.cover}
                coverCard={slide.content!.cards[0]}
                date={slide.date}
                media={bundledMedia}
                isActive={isActive}
                shouldLoadImage={shouldLoadImage}
                isDateBreak={slide.editionIndex > 0}
              />
            );
          }
          if (slide.kind === 'trending') {
            return (
              <TrendingSlide key={slide.key} trending={slide.content!.trending!} isActive={isActive} />
            );
          }
          if (slide.kind === 'closing') {
            return (
              <ClosingSlide
                key={slide.key}
                closing={slide.content!.closing}
                isActive={isActive}
                onRestart={() => goTo(index - (slide.localTotal - 1))}
                hasNextEdition={hasMore || index < slides.length - 1}
              />
            );
          }
          return (
            <CardSlide
              key={slide.key}
              card={slide.card!}
              date={slide.date}
              total={slide.content!.cards.length}
              media={bundledMedia}
              isActive={isActive}
              shouldLoadImage={shouldLoadImage}
              onOpenDetail={() => setSheetCard(slide.card)}
            />
          );
        })}
      </div>

      {cappedByLimit && (
        <p className="feed-error">더 이전 날짜는 위쪽 날짜 칩의 달력에서 골라주세요.</p>
      )}

      <DetailSheet card={sheetCard} onClose={() => setSheetCard(null)} />
    </div>
  );
}
