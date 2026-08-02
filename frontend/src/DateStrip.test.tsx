import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom';
import { DateStrip } from './DateStrip';

const editions = [
  { date: '2026-07-30', slug: 'btc-daily-0730', title: '비트코인 하이라이트 · 7.30' },
  { date: '2026-07-31', slug: 'btc-daily-0731', title: '비트코인 하이라이트 · 7.31' },
];

function mockFetch(data: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: status < 400,
      status,
      json: () => Promise.resolve(data),
    } as Response),
  );
}

function RouteDate() {
  const { date } = useParams();
  return <div data-testid="route-date">{date}</div>;
}

function renderStrip(activeDate: string) {
  return render(
    <MemoryRouter initialEntries={[`/d/${activeDate}`]}>
      <Routes>
        <Route
          path="/d/:date"
          element={
            <>
              <DateStrip activeDate={activeDate} />
              <RouteDate />
            </>
          }
        />
        <Route path="/calendar" element={<div data-testid="route-date">calendar</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('DateStrip', () => {
  it('renders a pill per edition and marks the active one', async () => {
    mockFetch(editions);
    const { container } = renderStrip('2026-07-31');

    const pills = await screen.findAllByRole('button');
    expect(pills).toHaveLength(3); // 2 date pills + the calendar icon button
    expect(container.querySelector('.strip-active')?.textContent).toBe('07.31');
  });

  it('navigates to the clicked date', async () => {
    mockFetch(editions);
    renderStrip('2026-07-31');

    const pills = await screen.findAllByRole('button');
    fireEvent.click(pills[0]);

    expect((await screen.findByTestId('route-date')).textContent).toBe('2026-07-30');
  });

  it('opens a calendar popover when the calendar icon button is clicked', async () => {
    mockFetch(editions);
    const { container } = renderStrip('2026-07-31');

    await screen.findAllByRole('button');
    const calendarBtn = container.querySelector('[aria-label="달력 보기"]');
    expect(calendarBtn).not.toBeNull();
    expect(container.querySelector('.cal-popover')).toBeNull();

    fireEvent.click(calendarBtn as Element);
    expect(container.querySelector('.cal-popover')).not.toBeNull();
  });

  it('navigates to /d/:date when a date is picked from the popover', async () => {
    // MonthCalendar defaults its view to `new Date()` — pin the clock so the
    // popover opens on July 2026 regardless of when this test actually runs.
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-07-31T12:00:00Z'));

    mockFetch(editions);
    const { container } = renderStrip('2026-07-31');

    await screen.findAllByRole('button');
    fireEvent.click(container.querySelector('[aria-label="달력 보기"]') as Element);

    const publishedDay = container.querySelector('.cal-published') as Element;
    fireEvent.click(publishedDay);

    expect((await screen.findByTestId('route-date')).textContent).toBe('2026-07-30');
    expect(container.querySelector('.cal-popover')).toBeNull();

    vi.useRealTimers();
  });
});
