import type { EditionContent } from './content';

export interface EditionSummary {
  date: string;
  slug: string;
  title: string;
}

export class NotFoundError extends Error {}

async function request<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path);
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

export function fetchLatestEdition(): Promise<EditionContent> {
  return request('/api/editions/latest');
}

export function fetchEdition(date: string): Promise<EditionContent> {
  return request(`/api/editions/${date}`);
}

export function errorMessage(err: unknown): string {
  if (err instanceof NotFoundError) return '존재하지 않는 날짜입니다.';
  if (err instanceof Error) return err.message;
  return '알 수 없는 오류가 발생했습니다.';
}
