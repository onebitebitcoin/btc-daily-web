import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { FeedNav } from './FeedNav';

function renderNav(overrides: Partial<Parameters<typeof FeedNav>[0]> = {}) {
  const onPrev = vi.fn();
  const onNext = vi.fn();
  render(
    <FeedNav
      onPrev={onPrev}
      onNext={onNext}
      atStart={false}
      atEnd={false}
      busy={false}
      {...overrides}
    />,
  );
  return {
    onPrev,
    onNext,
    up: screen.getByLabelText('이전 카드'),
    down: screen.getByLabelText('다음 카드'),
  };
}

describe('FeedNav', () => {
  it('아래 버튼이 다음 카드로 넘긴다', () => {
    const { down, onNext } = renderNav();

    fireEvent.click(down);

    expect(onNext).toHaveBeenCalledTimes(1);
  });

  it('위 버튼이 이전 카드로 넘긴다', () => {
    const { up, onPrev } = renderNav();

    fireEvent.click(up);

    expect(onPrev).toHaveBeenCalledTimes(1);
  });

  it('첫 슬라이드에서는 위로 갈 수 없다', () => {
    const { up, down } = renderNav({ atStart: true });

    expect((up as HTMLButtonElement).disabled).toBe(true);
    expect((down as HTMLButtonElement).disabled).toBe(false);
  });

  it('마지막 슬라이드에서는 아래로 갈 수 없다', () => {
    const { up, down } = renderNav({ atEnd: true });

    expect((down as HTMLButtonElement).disabled).toBe(true);
    expect((up as HTMLButtonElement).disabled).toBe(false);
  });

  it('끝에 닿아도 버튼을 감추지 않는다 — 사라지면 자리가 밀려 오조작이 난다', () => {
    renderNav({ atStart: true, atEnd: true });

    expect(screen.queryByLabelText('이전 카드')).not.toBeNull();
    expect(screen.queryByLabelText('다음 카드')).not.toBeNull();
  });

  it('비활성 버튼은 눌러도 아무 일이 없다', () => {
    const { down, onNext } = renderNav({ atEnd: true });

    fireEvent.click(down);

    expect(onNext).not.toHaveBeenCalled();
  });

  it('이모지 대신 아이콘을 쓴다 (프로젝트 UI 규칙)', () => {
    const { up } = renderNav();

    expect(up.querySelector('svg')).not.toBeNull();
    expect(up.textContent).toBe('');
  });

  it('이동이 도는 동안에는 두 버튼 모두 눌리지 않는다', () => {
    // 연달아 누르면 애니메이션이 끝나기 전에 다음 이동이 겹쳐 시작되어, 화면이
    // 어디로 갈지 예측할 수 없어진다.
    const { up, down, onPrev, onNext } = renderNav({ busy: true });

    expect((up as HTMLButtonElement).disabled).toBe(true);
    expect((down as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(down);
    fireEvent.click(up);

    expect(onNext).not.toHaveBeenCalled();
    expect(onPrev).not.toHaveBeenCalled();
  });

  it('이동이 끝나면 다시 눌린다', () => {
    const { down } = renderNav({ busy: false });

    expect((down as HTMLButtonElement).disabled).toBe(false);
  });
});
