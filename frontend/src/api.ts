import type { EditionContent } from './content';

export interface EditionSummary {
  date: string;
  slug: string;
  title: string;
}

export class NotFoundError extends Error {}

async function request<T>(path: string, method = 'GET'): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, method === 'GET' ? undefined : { method });
  } catch {
    throw new Error('서버에 연결할 수 없습니다.');
  }
  if (res.status === 404) throw new NotFoundError('찾을 수 없습니다.');
  if (!res.ok) throw new Error(`요청이 실패했습니다 (${res.status}).`);
  return res.json() as Promise<T>;
}

export function fetchEditions(): Promise<EditionSummary[]> {
  return request('/api/editions');
}

export function fetchEdition(date: string): Promise<EditionContent> {
  return request(`/api/editions/${date}`);
}

/** 카드 번호(`card.num`)를 키로 한 좋아요 수. 아무도 안 누른 카드는 키가 없다. */
export type CardLikeCounts = Record<string, number>;

export interface CardLikeResult {
  num: number;
  count: number;
}

export function fetchLikes(date: string): Promise<CardLikeCounts> {
  return request(`/api/editions/${date}/likes`);
}

export function likeCard(date: string, num: number): Promise<CardLikeResult> {
  return request(`/api/editions/${date}/cards/${num}/like`, 'POST');
}

export function unlikeCard(date: string, num: number): Promise<CardLikeResult> {
  return request(`/api/editions/${date}/cards/${num}/like`, 'DELETE');
}

export function errorMessage(err: unknown): string {
  if (err instanceof NotFoundError) return '존재하지 않는 날짜입니다.';
  if (err instanceof Error) return err.message;
  return '알 수 없는 오류가 발생했습니다.';
}
