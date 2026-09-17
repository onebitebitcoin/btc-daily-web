/** 이 브라우저가 어떤 카드에 좋아요를 눌렀는지 기억한다.
 *
 *  로그인이 없으므로 "누가 눌렀는지"를 서버에 남기지 않는다. 서버는 숫자만 세고,
 *  중복을 막는 기억은 여기 브라우저에만 둔다. 브라우저 데이터를 지우거나 다른
 *  기기로 오면 다시 누를 수 있다는 한계는 개인 정보를 한 건도 저장하지 않는 대가로
 *  받아들인 것이다.
 *
 *  읽기와 쓰기를 모두 try/catch 로 감싼다. 사파리 프라이빗 모드에서는 localStorage
 *  에 접근하는 것만으로 예외가 난다. 저장소를 못 쓰는 환경에서도 화면은 그대로
 *  동작해야 하고, 그때는 중복 방지만 포기한다.
 */

const STORAGE_KEY = 'btc-daily:likes';

/** 날짜와 카드 번호를 한 키로 합친다. `card.num` 은 에디션 안에서만 유일하다. */
const entryKey = (date: string, num: number) => `${date}:${num}`;

function readAll(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    // 남이 심어놓았거나 옛 형식이 남은 값일 수 있다. 객체가 아니면 버린다.
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {};
    return parsed as Record<string, boolean>;
  } catch {
    return {};
  }
}

function writeAll(entries: Record<string, boolean>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // 용량이 찼거나 접근이 막힌 환경 — 이번 세션에서는 중복 방지를 포기한다.
  }
}

export function hasLiked(date: string, num: number): boolean {
  return readAll()[entryKey(date, num)] === true;
}

/** 그 날짜에 이 브라우저가 누른 카드 번호들. */
export function likedNums(date: string): Set<number> {
  const prefix = `${date}:`;
  const liked = new Set<number>();
  for (const [key, value] of Object.entries(readAll())) {
    if (!value || !key.startsWith(prefix)) continue;
    const num = Number(key.slice(prefix.length));
    if (Number.isInteger(num)) liked.add(num);
  }
  return liked;
}

export function setLiked(date: string, num: number, liked: boolean): void {
  const entries = readAll();
  const key = entryKey(date, num);
  // 취소는 false 로 덮지 않고 키를 지운다 — 안 그러면 취소한 카드가 영원히 쌓인다.
  if (liked) entries[key] = true;
  else delete entries[key];
  writeAll(entries);
}
