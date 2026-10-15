import { h, render } from 'preact'
import { act } from 'preact/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Study } from './study'
import type { StudyCard } from './api'
import { setToastHandler } from './toast'

vi.mock('./useCategories', () => ({
  useCategory: () => ({ category: { id: 1, name: 'Test deck' }, ready: true, missing: false, error: null }),
}))

const cards: StudyCard[] = [1, 2, 3].map((id) => ({
  word_id: id,
  mode: 'pinyin_to_en',
  answer_chinese: `word-${id}`,
  answer_pinyin: `pinyin-${id}`,
  answer_english: `answer-${id}`,
  example_chinese: '',
  example_pinyin: '',
  example_english: '',
}))

let host: HTMLDivElement
let toasts: string[]
let fetchMock: ReturnType<typeof vi.fn>

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((done) => { resolve = done })
  return { promise, resolve }
}

beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  toasts = []
  setToastHandler((message) => toasts.push(message))
  fetchMock = vi.fn((path: string) => {
    if (path === '/api/ratings/undo/') return Promise.resolve(new Response(null, { status: 204 }))
    return Promise.resolve(json({ undo_token: 'latest-undo-token' }))
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(async () => {
  await act(() => render(null, host))
  host.remove()
  setToastHandler(null)
  vi.unstubAllGlobals()
})

async function mount(sessionCards = cards) {
  fetchMock.mockResolvedValueOnce(json({
    category: { id: 1, name: 'Test deck' }, difficulties: ['beginner'],
    total: sessionCards.length, cards: sessionCards,
  }))
  await act(() => render(h(Study, { categoryId: 1, difficulties: ['beginner'] }), host))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
}

function undoButton() {
  return host.querySelector<HTMLButtonElement>('[aria-label="Undo last rating"]')!
}

async function click(selector: string) {
  const target = host.querySelector<HTMLElement>(selector)
  expect(target).not.toBeNull()
  await act(async () => {
    target!.click()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

async function grade(grade: 'easy' | 'hard') {
  await click('.reveal-target')
  await click(`.grade-zone.${grade}`)
}

it('restores the previous card, its answer, and progress after Easy', async () => {
  await mount()
  expect(undoButton().disabled).toBe(true)
  await grade('easy')
  expect(host.textContent).toContain('word-2')
  expect(host.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('1')

  await click('.study-undo')

  expect(host.textContent).toContain('word-1')
  expect(host.textContent).toContain('answer-1')
  expect(host.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('0')
  expect(undoButton().disabled).toBe(true)
  expect(fetchMock).toHaveBeenLastCalledWith('/api/ratings/undo/', expect.objectContaining({
    body: JSON.stringify({ undo_token: 'latest-undo-token' }),
  }))
})

it('removes the Hard reinsert and restores its progress before rerating', async () => {
  await mount()
  await grade('hard')
  expect((host.querySelector('.study-progress-hard') as HTMLElement).style.width).not.toBe('0%')
  await click('.study-undo')
  expect((host.querySelector('.study-progress-hard') as HTMLElement).style.width).toBe('0%')
  await click('.grade-zone.easy')
  await grade('easy')
  await grade('easy')
  expect(host.textContent).toContain('All caught up')
})

it('can undo the final card and rate it again', async () => {
  await mount([cards[0]!])
  await grade('easy')
  expect(host.textContent).toContain('All caught up')
  await click('.study-undo')
  expect(host.textContent).toContain('answer-1')
  expect(host.textContent).not.toContain('All caught up')
  await click('.grade-zone.easy')
  expect(host.textContent).toContain('All caught up')
  expect(undoButton().disabled).toBe(false)
})

it('undoes only the latest rating', async () => {
  await mount()
  await grade('easy')
  await grade('easy')
  await click('.study-undo')
  expect(host.textContent).toContain('answer-2')
  expect(host.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('1')
  expect(undoButton().disabled).toBe(true)
})

it('orders rapid saves and waits for the latest save before undoing', async () => {
  await mount()
  const first = deferredResponse()
  const second = deferredResponse()
  const undone = deferredResponse()
  fetchMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    .mockReturnValueOnce(undone.promise)
  await grade('easy')
  await grade('easy')
  expect(host.textContent).toContain('word-3')
  expect(fetchMock).toHaveBeenCalledTimes(2) // Session + first save.
  await click('.study-undo')
  expect(undoButton().textContent).toContain('Undoing')
  expect(undoButton().disabled).toBe(true)

  await act(async () => {
    first.resolve(json({ undo_token: 'first' }))
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  expect(fetchMock).toHaveBeenLastCalledWith('/api/ratings/', expect.objectContaining({
    body: JSON.stringify({ word_id: 2, grade: 'easy' }),
  }))
  await act(async () => {
    second.resolve(json({ undo_token: 'second' }))
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  expect(fetchMock).toHaveBeenLastCalledWith('/api/ratings/undo/', expect.objectContaining({
    body: JSON.stringify({ undo_token: 'second' }),
  }))
  expect(host.textContent).toContain('word-3')
  await click('.reveal-target')
  expect(host.querySelector<HTMLButtonElement>('.grade-zone.easy')?.disabled).toBe(true)
  await act(async () => {
    undone.resolve(new Response(null, { status: 204 }))
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  expect(host.textContent).toContain('answer-2')
})

it('keeps the current card on undo failure and allows retry', async () => {
  await mount()
  await grade('easy')
  fetchMock.mockResolvedValueOnce(json({}, 500))
  await click('.study-undo')
  expect(host.textContent).toContain('word-2')
  expect(undoButton().disabled).toBe(false)
  expect(toasts).toEqual(['Couldn’t undo the rating. Try again.'])
  await click('.study-undo')
  expect(host.textContent).toContain('answer-1')
})

it('keeps the checkpoint when undo is rejected', async () => {
  await mount()
  await grade('easy')
  fetchMock.mockResolvedValueOnce(json({}, 400))
  await click('.study-undo')
  expect(host.textContent).toContain('word-2')
  expect(toasts).toEqual(['Couldn’t undo the rating. Try again.'])
  expect(undoButton().disabled).toBe(false)
})

it('disables undo when the latest rating could not be saved', async () => {
  await mount()
  const saving = deferredResponse()
  fetchMock.mockReturnValueOnce(saving.promise)
  await grade('easy')
  await click('.study-undo')
  await act(async () => {
    saving.resolve(json({}, 500))
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  expect(undoButton().disabled).toBe(true)
  expect(host.textContent).toContain('word-2')
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(toasts).toEqual(['Couldn’t save your progress. You can keep studying.'])
})

it('allows later ratings to save after a save failure', async () => {
  await mount()
  fetchMock.mockResolvedValueOnce(json({}, 500))
  await grade('easy')
  await grade('easy')
  await click('.study-undo')
  expect(host.textContent).toContain('answer-2')
  expect(toasts).toEqual(['Couldn’t save your progress. You can keep studying.'])
})
