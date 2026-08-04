import { Fragment } from 'react';
import hanipLogo from '../assets/brand/hanip-logo.jpg';
import type { Closing } from '../content';

interface ClosingSlideProps {
  closing: Closing;
  isActive: boolean;
  onRestart: () => void;
  /** 아래에 이어질 과거 에디션이 있으면 계속 내려가라고 안내한다. */
  hasNextEdition: boolean;
}

export function ClosingSlide({
  closing,
  isActive,
  onRestart,
  hasNextEdition,
}: ClosingSlideProps) {
  const lines = closing.mark_lines;
  const links = closing.links ?? [];

  return (
    <div className={'slide' + (isActive ? ' is-active' : '')} role="group">
      <div className="card is-closing">
        <div className="card-body">
          <span className="badge">{closing.eyebrow}</span>

          <h2 className="cover-mark closing-mark">
            {lines.slice(0, -1).map((l, i) => (
              <Fragment key={i}>
                {l}
                <br />
              </Fragment>
            ))}
            <em>{lines[lines.length - 1]}</em>
          </h2>

          {links.length > 0 && (
            <div className="closing-links">
              {links.map((l) => (
                <a
                  key={l.href}
                  className="closing-link"
                  href={l.href}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {l.label}
                </a>
              ))}
            </div>
          )}

          <span className="stamp">
            <img className="stamp-logo" src={hanipLogo} alt="" />
            {closing.stamp}
          </span>

          <button className="restart" type="button" onClick={onRestart}>
            {closing.restart}
          </button>

          {closing.sources && closing.sources.length > 0 && (
            // The content contract types sources as plain strings (no URLs), so
            // they render as text — the reference's <a> markup had nothing to link to.
            <div className="src-list">{'출처 — ' + closing.sources.join(' · ')}</div>
          )}

          <p className="disclaimer">{closing.disclaimer}</p>

          {hasNextEdition && (
            <div className="cover-hint next-hint">
              계속 올려서 지난 날짜 보기
              <span className="sw">
                <span />
                <span />
                <span />
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
