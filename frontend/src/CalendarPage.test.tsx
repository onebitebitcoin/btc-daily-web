import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom';
import CalendarPage from './CalendarPage';

const today = new Date();
const pad = (n: number) => String(n).padStart(2, '0');
const monthLabel = (date: Date) => `${date.getFullYear()}년 ${date.getMonth() + 1}월`;

// Day 1 and day 2 exist in every month, so these are safe regardless of when the test runs.
const publishedDate = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-01`;
const editions = [{ date: publishedDate, slug: 'btc-daily-01', title: '비트코인 하이라이트' }];

function mockFetch(data: unknown, status = 200) {
  const fn = vi.fn().mockResolvedValue({
    ok: status < 400,
    status,
    json: () => Promise.resolve(data),
  } as Response);
  vi.stubGlobal('fetch', fn);
  return fn;
}

function RouteDate() {
  const { date } = useParams();
  return <div data-testid="route-date">{date}</div>;
}

function renderCalendar() {
  return render(
    <MemoryRouter initialEntries={['/calendar']}>
      <Routes>
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="/d/:date" element={<RouteDate />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('CalendarPage', () => {
  it('renders a published date as a button and an unpublished date as a span', async () => {
    mockFetch(editions);
    renderCalendar();

    const published = await screen.findByText('1');
    expect(published.tagName).toBe('BUTTON');

    const unpublished = screen.getByText('2');
    expect(unpublished.tagName).toBe('SPAN');
  });

  it('navigates to /d/:date when a published date is clicked', async () => {
    mockFetch(editions);
    renderCalendar();

    const published = await screen.findByText('1');
    fireEvent.click(published);

    expect((await screen.findByTestId('route-date')).textContent).toBe(publishedDate);
  });

  it('changes the displayed month via prev/next without triggering another fetch', async () => {
    const fetchMock = mockFetch(editions);
    renderCalendar();

    await screen.findByText(monthLabel(today));

    const nextMonth = new Date(today.getFullYear(), today.getMonth() + 1, 1);
    fireEvent.click(screen.getByLabelText('다음 달'));
    expect(await screen.findByText(monthLabel(nextMonth))).toBeDefined();

    fireEvent.click(screen.getByLabelText('이전 달'));
    expect(await screen.findByText(monthLabel(today))).toBeDefined();

    const prevMonth = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    fireEvent.click(screen.getByLabelText('이전 달'));
    expect(await screen.findByText(monthLabel(prevMonth))).toBeDefined();

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('shows a loading message before data arrives', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    renderCalendar();

    expect(screen.getByText('불러오는 중…')).toBeDefined();
  });

  it('shows an error message via StatusScreen when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new Error('network down'))),
    );
    renderCalendar();

    expect(await screen.findByText('서버에 연결할 수 없습니다.')).toBeDefined();
  });
});
