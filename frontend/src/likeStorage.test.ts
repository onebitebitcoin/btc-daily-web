import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { hasLiked, likedNums, setLiked } from './likeStorage';

const DATE = '2026-09-18';

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('likeStorage', () => {
  it('누른 카드를 기억하고 취소하면 잊는다', () => {
    setLiked(DATE, 3, true);
    expect(hasLiked(DATE, 3)).toBe(true);

    setLiked(DATE, 3, false);
    expect(hasLiked(DATE, 3)).toBe(false);
  });

  it('취소한 카드는 키 자체를 지운다', () => {
    // false 로 덮어두면 취소한 카드가 저장소에 영원히 쌓인다.
    setLiked(DATE, 3, true);
    setLiked(DATE, 3, false);

    expect(JSON.parse(localStorage.getItem('btc-daily:likes') ?? '{}')).toEqual({});
  });

  it('날짜가 다르면 같은 번호라도 따로 센다', () => {
    // card.num 은 에디션 안에서만 유일하다. 날짜가 빠지면 어제 카드 1과 섞인다.
    setLiked(DATE, 1, true);

    expect(hasLiked('2026-09-17', 1)).toBe(false);
  });

  it('그 날짜에 누른 번호만 모아 준다', () => {
    setLiked(DATE, 1, true);
    setLiked(DATE, 4, true);
    setLiked('2026-09-17', 2, true);

    expect(likedNums(DATE)).toEqual(new Set([1, 4]));
  });

  it('저장소에 깨진 값이 있어도 빈 상태로 시작한다', () => {
    localStorage.setItem('btc-daily:likes', '[1,2,3]');

    expect(likedNums(DATE)).toEqual(new Set());
    expect(hasLiked(DATE, 1)).toBe(false);
  });

  it('저장소를 못 쓰는 환경에서도 예외를 밖으로 내보내지 않는다', () => {
    // 사파리 프라이빗 모드는 접근만으로 예외를 던진다. 중복 방지는 포기하되
    // 화면은 그대로 동작해야 한다.
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });

    expect(() => setLiked(DATE, 1, true)).not.toThrow();
    expect(hasLiked(DATE, 1)).toBe(false);
    expect(likedNums(DATE)).toEqual(new Set());
  });
});
