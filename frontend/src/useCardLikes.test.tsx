import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { useCardLikes, likeKey } from './useCardLikes';
import { hasLiked } from './likeStorage';

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return {
    ...actual,
    fetchLikes: vi.fn(),
    likeCard: vi.fn(),
    unlikeCard: vi.fn(),
  };
});

const api = await import('./api');
const fetchLikes = vi.mocked(api.fetchLikes);
const likeCard = vi.mocked(api.likeCard);
const unlikeCard = vi.mocked(api.unlikeCard);

const DATE = '2026-09-18';

/** 훅 상태를 화면에 찍고, 버튼으로 토글을 부른다. */
function Likes({ dates }: { dates: string[] }) {
  const { counts, mine, error, toggle } = useCardLikes(dates);
  const key = likeKey(DATE, 1);
  return (
    <div>
      <span data-testid="count">{counts[key] ?? 0}</span>
      <span data-testid="mine">{mine.has(key) ? 'yes' : 'no'}</span>
      <span data-testid="error">{error ?? ''}</span>
      <button onClick={() => toggle(DATE, 1)}>toggle</button>
    </div>
  );
}

const count = () => screen.getByTestId('count').textContent;
const mine = () => screen.getByTestId('mine').textContent;
const error = () => screen.getByTestId('error').textContent;

async function clickToggle() {
  await act(async () => {
    screen.getByText('toggle').click();
  });
}

beforeEach(() => {
  localStorage.clear();
  fetchLikes.mockResolvedValue({});
  likeCard.mockResolvedValue({ num: 1, count: 1 });
  unlikeCard.mockResolvedValue({ num: 1, count: 0 });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('useCardLikes', () => {
  it('피드에 실린 날짜를 모두 조회한다', async () => {
    render(<Likes dates={[DATE, '2026-09-17']} />);

    await waitFor(() => expect(fetchLikes).toHaveBeenCalledTimes(2));
    expect(fetchLikes).toHaveBeenCalledWith(DATE);
    expect(fetchLikes).toHaveBeenCalledWith('2026-09-17');
  });

  it('이미 받은 날짜는 다시 조회하지 않는다', async () => {
    // 피드를 위아래로 오갈 때마다 같은 날짜를 다시 받으면 요청이 쌓인다.
    const { rerender } = render(<Likes dates={[DATE]} />);
    await waitFor(() => expect(fetchLikes).toHaveBeenCalledTimes(1));

    rerender(<Likes dates={[DATE, '2026-09-17']} />);

    await waitFor(() => expect(fetchLikes).toHaveBeenCalledTimes(2));
    expect(fetchLikes).toHaveBeenLastCalledWith('2026-09-17');
  });

  it('서버가 준 수치를 화면에 올린다', async () => {
    fetchLikes.mockResolvedValue({ '1': 7 });

    render(<Likes dates={[DATE]} />);

    await waitFor(() => expect(count()).toBe('7'));
  });

  it('누르면 화면 숫자가 먼저 오르고 저장소에 남는다', async () => {
    fetchLikes.mockResolvedValue({ '1': 4 });
    likeCard.mockResolvedValue({ num: 1, count: 5 });
    render(<Likes dates={[DATE]} />);
    await waitFor(() => expect(count()).toBe('4'));

    await clickToggle();

    expect(count()).toBe('5');
    expect(mine()).toBe('yes');
    expect(hasLiked(DATE, 1)).toBe(true);
  });

  it('서버가 센 값으로 최종 수치를 맞춘다', async () => {
    // 같은 순간 다른 사람이 눌렀으면 낙관적 수치와 어긋난다. 서버 값이 진짜다.
    fetchLikes.mockResolvedValue({ '1': 4 });
    likeCard.mockResolvedValue({ num: 1, count: 9 });
    render(<Likes dates={[DATE]} />);
    await waitFor(() => expect(count()).toBe('4'));

    await clickToggle();

    await waitFor(() => expect(count()).toBe('9'));
  });

  it('요청이 실패하면 수치와 저장소를 되돌리고 사유를 알린다', async () => {
    fetchLikes.mockResolvedValue({ '1': 4 });
    likeCard.mockRejectedValue(new Error('서버에 연결할 수 없습니다.'));
    render(<Likes dates={[DATE]} />);
    await waitFor(() => expect(count()).toBe('4'));

    await clickToggle();

    await waitFor(() => expect(error()).toBe('서버에 연결할 수 없습니다.'));
    expect(count()).toBe('4');
    expect(mine()).toBe('no');
    expect(hasLiked(DATE, 1)).toBe(false);
  });

  it('다시 누르면 취소된다', async () => {
    fetchLikes.mockResolvedValue({ '1': 4 });
    likeCard.mockResolvedValue({ num: 1, count: 5 });
    unlikeCard.mockResolvedValue({ num: 1, count: 4 });
    render(<Likes dates={[DATE]} />);
    await waitFor(() => expect(count()).toBe('4'));

    await clickToggle();
    await clickToggle();

    expect(unlikeCard).toHaveBeenCalledWith(DATE, 1);
    await waitFor(() => expect(count()).toBe('4'));
    expect(mine()).toBe('no');
    expect(hasLiked(DATE, 1)).toBe(false);
  });

  it('저장소가 기억한 카드는 처음부터 누른 상태다', async () => {
    localStorage.setItem('btc-daily:likes', JSON.stringify({ [`${DATE}:1`]: true }));
    fetchLikes.mockResolvedValue({ '1': 4 });

    render(<Likes dates={[DATE]} />);

    await waitFor(() => expect(mine()).toBe('yes'));
  });

  it('좋아요 수를 못 받아도 화면은 그대로 뜬다', async () => {
    // 카드 본문은 읽을 수 있어야 한다. 숫자만 비워 둔다.
    fetchLikes.mockRejectedValue(new Error('down'));

    render(<Likes dates={[DATE]} />);

    await waitFor(() => expect(fetchLikes).toHaveBeenCalled());
    expect(count()).toBe('0');
    expect(error()).toBe('');
  });
});
