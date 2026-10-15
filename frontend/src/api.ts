import { reportApiFailure } from './monitoring'
import { showToast } from './toast'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

export type AuthUser = {
  authenticated: true
  email: string
}

export type AuthState =
  | AuthUser
  | {
      authenticated: false
      email: null
    }

type RequestOptions = {
  method?: string
  body?: unknown
  /** Toast the failure. Off by default so screens with their own error UI stay silent. */
  toast?: boolean
}

function messageFromErrorBody(data: unknown): string {
  if (!data || typeof data !== 'object') {
    return 'Request failed'
  }

  const body = data as Record<string, unknown>
  const detail = body.detail

  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail)) {
    const parts = detail.filter((item): item is string => typeof item === 'string')
    if (parts.length > 0) {
      return parts.join(' ')
    }
  }

  const fieldMessages: string[] = []
  for (const [key, value] of Object.entries(body)) {
    if (key === 'detail') continue
    if (Array.isArray(value)) {
      const first = value.find((item): item is string => typeof item === 'string')
      if (first) fieldMessages.push(first)
    } else if (typeof value === 'string') {
      fieldMessages.push(value)
    }
  }

  return fieldMessages.length > 0 ? fieldMessages.join(' ') : 'Request failed'
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = {
    Accept: 'application/json',
  }

  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  if (method !== 'GET' && method !== 'HEAD') {
    const csrf = getCookie('csrftoken')
    if (csrf) {
      headers['X-CSRFToken'] = csrf
    }
  }

  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: 'same-origin',
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    })
  } catch (err) {
    reportApiFailure(method, path)
    if (options.toast) {
      showToast('Could not reach the server.')
    }
    throw err
  }

  if (!response.ok) {
    if (response.status >= 500) reportApiFailure(method, path, response.status)
    let message = 'Request failed'
    try {
      message = messageFromErrorBody(await response.json())
    } catch {
      // ignore non-JSON error bodies
    }
    if (options.toast) {
      showToast(message)
    }
    throw new ApiError(response.status, message)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch('/api/health/', {
      method: 'GET',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
    return response.ok
  } catch {
    return false
  }
}

export function fetchMe(): Promise<AuthState> {
  return apiRequest<AuthState>('/api/auth/me/')
}

export function login(email: string, password: string): Promise<AuthUser> {
  return apiRequest<AuthUser>('/api/auth/login/', {
    method: 'POST',
    body: { email, password },
  })
}

export function logout(): Promise<AuthState> {
  return apiRequest<AuthState>('/api/auth/logout/', { method: 'POST' })
}

export type Category = {
  id: number
  name: string
  novice_count: number
  intermediate_count: number
  advanced_count: number
  expert_count: number
  last_practiced_at: string | null
}

export type Difficulty = 'novice' | 'intermediate' | 'advanced' | 'expert'

export type StudyCard = {
  word_id: number
  mode: string
  answer_chinese: string
  answer_pinyin: string
  answer_english: string
  example_chinese: string
  example_pinyin: string
  example_english: string
}

export type StudySession = {
  category: { id: number; name: string }
  difficulties: Difficulty[]
  total: number
  cards: StudyCard[]
}

export function fetchCategories(): Promise<Category[]> {
  return apiRequest<Category[]>('/api/categories/')
}

export function createSession(
  categoryId: number,
  difficulties: Difficulty[],
): Promise<StudySession> {
  return apiRequest<StudySession>('/api/sessions/', {
    method: 'POST',
    body: { category_id: categoryId, difficulties },
  })
}

export type CardGrade = 'hard' | 'easy'

export async function rateCard(wordId: number, grade: CardGrade): Promise<void> {
  try {
    await apiRequest('/api/ratings/', {
      method: 'POST',
      body: { word_id: wordId, grade },
    })
  } catch (err) {
    showToast(
      err instanceof ApiError && err.status === 401
        ? 'Your session expired. Sign in again to save progress.'
        : 'Couldn’t save your progress. You can keep studying.',
    )
    throw err
  }
}

export async function flagWord(wordId: number): Promise<void> {
  try {
    await apiRequest('/api/word-flags/', {
      method: 'POST',
      body: { word_id: wordId },
    })
    showToast('Marked for review')
  } catch (err) {
    showToast(
      err instanceof ApiError && err.status === 401
        ? 'Your session expired. Sign in again.'
        : 'Couldn’t flag this card. Try again.',
    )
    throw err
  }
}
