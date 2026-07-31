import { Fragment } from 'react';
import { useSwipeDeck } from './useSwipeDeck';
import { useThemeVars, type Theme } from './useThemeVars';
import './deck.css';
import './qa.css';

export interface Cover {
  eyebrow: string;
  mark: string[];
  meta: string[];
  hint: string;
}

export interface Card {
  num: number;
  chip: { text: string; emphasis: 'primary' | 'secondary' | null } | null;
  title: string;
  subtitle: string | null;
  chips_label: string | null;
  chips: string[] | null;
  body: string;
  quote: string | null;
  link: { label: string; href: string } | null;
  media: { image: string; href: string | null; cta: string | null } | null;
  qa?: { question: string; answer: string; sources: string[] }[] | null;
}

export interface Closing {
  eyebrow: string;
  mark_lines: string[];
  rows: string[][];
  stamp: string;
  restart: string;
  sources: string[];
}

export interface EditionContent {
  meta: { title: string; slug: string; date: string };
  theme: Theme;
  brand: string;
  cover: Cover;
  cards: Card[];
  closing: Closing;
}

interface CardDeckProps {
  content: EditionContent;
  media: Record<string, string>;
}

const pad2 = (n: number) => String(n).padStart(2, '0');

const emphClass = (emphasis: string | null) =>
  emphasis === 'primary' ? ' emph-a' : emphasis === 'secondary' ? ' emph-b' : '';

function CoverSlide({ cover, isActive }: { cover: Cover; isActive: boolean }) {
  return (
    <div className={'slide' + (isActive ? ' is-active' : '')} role="group">
      <div className="card is-cover">
        <div className="card-inner">
          <span className="badge">{cover.eyebrow}</span>
          <h1 className="cover-mark">
            {cover.mark.map((line, i) => (
              <Fragment key={i}>
                {i > 0 && <br />}
                {line}
              </Fragment>
            ))}
          </h1>
          <p className="cover-meta">
            {cover.meta.map((x, i) => (
              <span key={i}>{x}</span>
            ))}
          </p>
          <div className="cover-hint">
            {cover.hint}{' '}
            <span className="sw">
              <span />
              <span />
              <span />
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function CardArt({ card, media }: { card: Card; media: Record<string, string> }) {
  if (!card.media) return null;
  const key = card.media.image;
  const src = key ? (media[key] ?? (/^https?:\/\//.test(key) ? key : undefined)) : undefined;
  if (!src) return <div className="art art-blank">{pad2(card.num)}</div>;

  const img = <img src={src} alt={card.title} loading="lazy" />;
  const badge =
    card.media.href && card.media.cta ? (
      <span className="art-badge">
        <span className="tri" />
        {card.media.cta}
      </span>
    ) : null;

  return card.media.href ? (
    <a className="art is-link" href={card.media.href} target="_blank" rel="noopener">
      {img}
      {badge}
    </a>
  ) : (
    <div className="art">{img}</div>
  );
}

function CardSlide({
  card,
  total,
  media,
  isActive,
}: {
  card: Card;
  total: number;
  media: Record<string, string>;
  isActive: boolean;
}) {
  return (
    <div className={'slide' + (isActive ? ' is-active' : '')} role="group">
      <div className="card">
        <div className="card-scroll">
          <div className="card-inner">
            <div className="card-head">
              <span className="card-num">
                {pad2(card.num)} / {total}
              </span>
              {card.chip && (
                <span className={'badge' + emphClass(card.chip.emphasis)}>{card.chip.text}</span>
              )}
            </div>

            <CardArt card={card} media={media} />

            <div className="titles">
              <div className="primary">{card.title}</div>
              {card.subtitle && <div className="secondary">{card.subtitle}</div>}
            </div>

            {card.chips && card.chips.length > 0 && (
              <div className="chips-row">
                {card.chips_label && <span className="cl">{card.chips_label}</span>}
                {card.chips.map((c, i) => (
                  <span className="chip" key={i}>
                    {c}
                  </span>
                ))}
              </div>
            )}

            <p className="body-text">{card.body}</p>

            {card.quote && <p className="pull">{'“' + card.quote + '”'}</p>}

            {card.link && (
              <a className="link-cta" href={card.link.href} target="_blank" rel="noopener">
                <span className="tri" />
                {card.link.label}
              </a>
            )}

            {card.qa && (
              <div className="qa-block">
                <p className="qa-label">생각 확장하기</p>
                {card.qa.map((q, i) => (
                  <details className="qa-item" key={i}>
                    <summary>{q.question}</summary>
                    <p>{q.answer}</p>
                    {q.sources.length > 0 && (
                      <ul className="qa-sources">
                        {q.sources.map((url, si) => (
                          <li key={si}>
                            <a href={url} target="_blank" rel="noopener">
                              출처 {si + 1}
                            </a>
                          </li>
                        ))}
                      </ul>
                    )}
                  </details>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ClosingSlide({
  closing,
  isActive,
  onRestart,
}: {
  closing: Closing;
  isActive: boolean;
  onRestart: () => void;
}) {
  const lines = closing.mark_lines;
  return (
    <div className={'slide' + (isActive ? ' is-active' : '')} role="group">
      <div className="card is-closing">
        <div className="card-inner">
          <span className="badge">{closing.eyebrow}</span>

          <h2 className="cover-mark" style={{ fontSize: '30px' }}>
            {lines.slice(0, -1).map((l, i) => (
              <Fragment key={i}>
                {l}
                <br />
              </Fragment>
            ))}
            <em>{lines[lines.length - 1]}</em>
          </h2>

          <div className="totals">
            {closing.rows.map((row, i) => (
              <div className="trow" key={i}>
                <span>{row[0]}</span>
                <b>{row[1]}</b>
              </div>
            ))}
          </div>

          <span className="stamp">{closing.stamp}</span>

          <button className="restart" type="button" onClick={onRestart}>
            {closing.restart}
          </button>

          {closing.sources && closing.sources.length > 0 && (
            // The content contract types sources as plain strings (no URLs), so
            // they render as text — the reference's <a> markup had nothing to link to.
            <div className="src-list">{'출처 — ' + closing.sources.join(' · ')}</div>
          )}
        </div>
      </div>
    </div>
  );
}

export function CardDeck({ content, media }: CardDeckProps) {
  const { brand, cover, cards, closing, theme } = content;
  const total = cards.length + 2;
  const { current, trackRef, goTo, prev, next } = useSwipeDeck(total);

  useThemeVars(theme);

  return (
    <div className="app">
      <div className="progress-bar">
        {Array.from({ length: total }, (_, i) => (
          <i key={i} className={i <= current ? 'done' : undefined} onClick={() => goTo(i)}>
            <b />
          </i>
        ))}
      </div>

      <div className="topline">
        <span className="brand">{brand}</span>
        <span className="counter">
          {pad2(current + 1)} / {total}
        </span>
      </div>

      <button
        className="nav-btn prev"
        aria-label="이전 카드"
        type="button"
        disabled={current === 0}
        onClick={prev}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </button>
      <button
        className="nav-btn next"
        aria-label="다음 카드"
        type="button"
        disabled={current === total - 1}
        onClick={next}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M9 18l6-6-6-6" />
        </svg>
      </button>

      <div className="track" ref={trackRef}>
        <CoverSlide cover={cover} isActive={current === 0} />
        {cards.map((card, i) => (
          <CardSlide
            key={card.num}
            card={card}
            total={cards.length}
            media={media}
            isActive={current === i + 1}
          />
        ))}
        <ClosingSlide
          closing={closing}
          isActive={current === total - 1}
          onRestart={() => goTo(0)}
        />
      </div>
    </div>
  );
}
