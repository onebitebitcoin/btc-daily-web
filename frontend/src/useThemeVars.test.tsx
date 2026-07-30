import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { buildThemeCss, useThemeVars, type Theme } from './useThemeVars';

function Themed({ theme }: { theme: Theme }) {
  useThemeVars(theme);
  return null;
}

const injectedCss = () =>
  Array.from(document.head.querySelectorAll('style'))
    .map((s) => s.textContent ?? '')
    .join('\n');

describe('buildThemeCss', () => {
  it('maps snake_case theme keys to kebab-case custom properties', () => {
    expect(buildThemeCss({ bg: '#181410', accent_strong: '#ffcf7f' })).toContain(
      ':root { --bg: #181410; --accent-strong: #ffcf7f; }',
    );
  });

  it('emits _light keys as light-theme overrides under the base name', () => {
    const css = buildThemeCss({ bg: '#181410', bg_light: '#e8e0d4' });
    expect(css).toContain(':root { --bg: #181410; }');
    expect(css).toContain(':root[data-theme="light"] { --bg: #e8e0d4; }');
    expect(css).toContain(
      '@media (prefers-color-scheme: light) { :root:not([data-theme="dark"]) { --bg: #e8e0d4; } }',
    );
  });

  // Inline styles on :root would outrank the light overrides, so the dark block
  // must be a rule that the later light rules can override.
  it('orders the dark block before the light overrides', () => {
    const css = buildThemeCss({ bg: '#181410', bg_light: '#e8e0d4' });
    expect(css.indexOf(':root {')).toBeLessThan(css.indexOf('prefers-color-scheme'));
  });

  it('drops values that would break out of the declaration block', () => {
    const css = buildThemeCss({ bg: '#181410', accent: 'red; } :root { display: none' });
    expect(css).toContain('--bg: #181410;');
    expect(css).not.toContain('display: none');
  });
});

describe('useThemeVars', () => {
  it('injects the theme stylesheet and swaps it when the theme changes', () => {
    const { rerender } = render(<Themed theme={{ bg: '#181410' }} />);
    expect(injectedCss()).toContain('--bg: #181410;');

    rerender(<Themed theme={{ bg: '#ffffff' }} />);
    expect(injectedCss()).toContain('--bg: #ffffff;');
    expect(injectedCss()).not.toContain('--bg: #181410;');
  });

  it('removes its stylesheet on unmount', () => {
    const { unmount } = render(<Themed theme={{ bg: '#181410' }} />);
    unmount();
    expect(injectedCss()).not.toContain('--bg: #181410;');
  });
});
