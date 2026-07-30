import { useEffect } from 'react';

export type Theme = Record<string, string>;

const LIGHT_SUFFIX = '_light';

/** Theme values reach the DOM as raw CSS text, so reject anything that could
 *  escape a declaration or the <style> element it is written into. */
const isSafe = (key: string, value: string) => /^[a-z0-9_]+$/i.test(key) && !/[;{}<]/.test(value);

const cssVar = (key: string) => `--${key.replace(/_/g, '-')}`;

function splitTheme(theme: Theme) {
  const dark: string[] = [];
  const light: string[] = [];
  for (const [key, value] of Object.entries(theme)) {
    if (!isSafe(key, value)) continue;
    if (key.endsWith(LIGHT_SUFFIX)) {
      light.push(`${cssVar(key.slice(0, -LIGHT_SUFFIX.length))}: ${value};`);
    } else {
      dark.push(`${cssVar(key)}: ${value};`);
    }
  }
  return { dark, light };
}

export function buildThemeCss(theme: Theme): string {
  const { dark, light } = splitTheme(theme);
  return [
    `:root { ${dark.join(' ')} }`,
    `:root[data-theme="light"] { ${light.join(' ')} }`,
    `@media (prefers-color-scheme: light) { :root:not([data-theme="dark"]) { ${light.join(' ')} } }`,
  ].join('\n');
}

/** Runtime equivalent of build.py's build_theme_css: the per-edition theme becomes
 *  a stylesheet, with `_light`-suffixed keys as light-theme overrides.
 *
 *  These have to be stylesheet rules rather than inline styles on :root — inline
 *  styles outrank any rule, so the light overrides would never apply. Source order
 *  is what lets them win, exactly as in the generated static page. */
export function useThemeVars(theme: Theme): void {
  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = buildThemeCss(theme);
    document.head.appendChild(style);
    return () => style.remove();
  }, [theme]);
}
