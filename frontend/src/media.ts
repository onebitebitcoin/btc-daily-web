// Bundled seed images, keyed by filename stem (e.g. 'fed-macro'). Editions served
// from the API may reference these stems (seed data) or full https URLs (auto
// publishing) — imageUrl.ts routes absolute URLs through the resizing proxy and
// only falls back to this map for seed stems.
export const bundledMedia: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob('./assets/media/*', { eager: true, query: '?url', import: 'default' }),
  ).map(([path, url]) => [path.replace(/^.*\/|\.[^.]+$/g, ''), url as string]),
);
