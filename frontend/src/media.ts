// Bundled seed images, keyed by filename stem (e.g. 'fed-macro'). Editions served
// from the API may reference these stems (seed data) or full https URLs (auto
// publishing) — imageUrl.ts routes absolute URLs through the resizing proxy and
// only falls back to this map for seed stems.
export const bundledMedia: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob('./assets/media/*', { eager: true, query: '?url', import: 'default' }),
  ).map(([path, url]) => [path.replace(/^.*\/|\.[^.]+$/g, ''), url as string]),
);

// 표지 인용구 화자의 초상, 같은 방식으로 stem('menger')을 키로 쓴다. 뉴스 이미지와
// 달리 원격 URL이 섞이지 않는다 — 퍼블릭 도메인 파일만 저장소에 두기 때문에 프록시가
// 필요 없고, 여기 없는 인물은 프론트가 이름을 조판한 아바타로 대신한다.
export const bundledPortraits: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob('./assets/portraits/*', { eager: true, query: '?url', import: 'default' }),
  ).map(([path, url]) => [path.replace(/^.*\/|\.[^.]+$/g, ''), url as string]),
);
