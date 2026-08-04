import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { MAX_FEED_EDITIONS, useEditionQueue } from './useEditionQueue';

const DATES = ['2026-07-28', '2026-07-29', '2026-07-30', '2026-07-31'];

function edition(date: string) {
  return { meta: { title: `T ${date}`, slug: `s-${date}`, date }, cards: [] };
}

/** /api/editions와 /api/editions/{date}를 구분해 응답하는 fetch 스텁. */
function stubApi(options: { failDates?: string[]; listFails?: boolean } = {}) {
  const calls: string[] = [];
  const fetchMock = vi.fn((path: string) => {
    calls.push(path);
    if (path === '/api/editions') {
      if (options.listFails) return Promise.reject(new TypeError('network down'));
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(DATES.map((d) => ({ date: d, slug: d, title: d }))),
      } as Response);
    }
    const date = path.replace('/api/editions/', '');
    if (options.failDates?.includes(date)) {
      return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) } as Response);
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(edition(date)),
    } as Response);
  });
  vi.stubGlobal('fetch', fetchMock);
  return calls;
}

let loadMore: () => void = () => {};

function Harness({ startDate, max }: { startDate: string; max?: number }) {
  const queue = useEditionQueue(startDate, max);
  loadMore = queue.loadMore;
  return (
    <div>
      <span data-testid="dates">{queue.entries.map((e) => e.date).join(',')}</span>
      <span data-testid="errors">
        {queue.entries.map((e) => `${e.date}:${e.error ?? 'ok'}`).join(',')}
      </span>
      <span data-testid="has-more">{String(queue.hasMore)}</span>
      <span data-testid="capped">{String(queue.cappedByLimit)}</span>
      <span data-testid="list-error">{queue.listError ?? ''}</span>
    </div>
  );
}

const dates = () => screen.getByTestId('dates').textContent;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useEditionQueue', () => {
  it('loads the start date first', async () => {
    stubApi();
    render(<Harness startDate="2026-07-31" />);

    await waitFor(() => expect(dates()).toBe('2026-07-31'));
  });

  it('appends progressively older dates on loadMore', async () => {
    stubApi();
    render(<Harness startDate="2026-07-31" />);
    await waitFor(() => expect(dates()).toBe('2026-07-31'));

    await act(async () => loadMore());
    await waitFor(() => expect(dates()).toBe('2026-07-31,2026-07-30'));

    await act(async () => loadMore());
    await waitFor(() => expect(dates()).toBe('2026-07-31,2026-07-30,2026-07-29'));
  });

  it('never walks forward into dates newer than the start date', async () => {
    stubApi();
    render(<Harness startDate="2026-07-29" />);
    await waitFor(() => expect(dates()).toBe('2026-07-29'));

    await act(async () => loadMore());

    await waitFor(() => expect(dates()).toBe('2026-07-29,2026-07-28'));
  });

  it('prefetches the next edition JSON before it is requested', async () => {
    const calls = stubApi();
    render(<Harness startDate="2026-07-31" />);

    await waitFor(() => expect(dates()).toBe('2026-07-31'));

    await waitFor(() => expect(calls).toContain('/api/editions/2026-07-30'));
    expect(dates()).toBe('2026-07-31');
  });

  it('serves an appended date from the prefetch cache instead of refetching', async () => {
    const calls = stubApi();
    render(<Harness startDate="2026-07-31" />);
    await waitFor(() => expect(calls).toContain('/api/editions/2026-07-30'));

    await act(async () => loadMore());
    await waitFor(() => expect(dates()).toBe('2026-07-31,2026-07-30'));

    expect(calls.filter((c) => c === '/api/editions/2026-07-30')).toHaveLength(1);
  });

  it('isolates a failed edition instead of killing the feed', async () => {
    stubApi({ failDates: ['2026-07-30'] });
    render(<Harness startDate="2026-07-31" />);
    await waitFor(() => expect(dates()).toBe('2026-07-31'));

    await act(async () => loadMore());
    await waitFor(() => expect(dates()).toBe('2026-07-31,2026-07-30'));
    expect(screen.getByTestId('errors').textContent).toContain('2026-07-30:요청이 실패했습니다');

    await act(async () => loadMore());
    await waitFor(() => expect(dates()).toBe('2026-07-31,2026-07-30,2026-07-29'));
  });

  it('stops at the edition cap and reports it', async () => {
    stubApi();
    render(<Harness startDate="2026-07-31" max={2} />);
    await waitFor(() => expect(dates()).toBe('2026-07-31'));

    await act(async () => loadMore());
    await waitFor(() => expect(dates()).toBe('2026-07-31,2026-07-30'));

    await act(async () => loadMore());
    await waitFor(() => expect(screen.getByTestId('has-more').textContent).toBe('false'));
    expect(dates()).toBe('2026-07-31,2026-07-30');
    expect(screen.getByTestId('capped').textContent).toBe('true');
  });

  it('does not report a cap when the feed simply ran out of editions', async () => {
    stubApi();
    render(<Harness startDate="2026-07-29" />);
    await waitFor(() => expect(dates()).toBe('2026-07-29'));

    await act(async () => loadMore());
    await waitFor(() => expect(screen.getByTestId('has-more').textContent).toBe('false'));

    expect(screen.getByTestId('capped').textContent).toBe('false');
  });

  it('surfaces a failure to load the published date list', async () => {
    stubApi({ listFails: true });
    render(<Harness startDate="2026-07-31" />);

    await waitFor(() =>
      expect(screen.getByTestId('list-error').textContent).toBe('서버에 연결할 수 없습니다.'),
    );
  });

  it('caps the feed at seven editions by default', () => {
    expect(MAX_FEED_EDITIONS).toBe(7);
  });
});
