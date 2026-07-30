import { CardDeck, type EditionContent } from './CardDeck';
import content from './fixtures/content.json';

// Phase 4 renders a local fixture; the API wiring lands in Phase 5.
const media: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob('./assets/media/*', { eager: true, query: '?url', import: 'default' }),
  ).map(([path, url]) => [path.replace(/^.*\/|\.[^.]+$/g, ''), url as string]),
);

export default function App() {
  return <CardDeck content={content as EditionContent} media={media} />;
}
