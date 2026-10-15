import * as Sentry from '@sentry/browser'
import { h, render } from 'preact'
import { act } from 'preact/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Study } from './study'

vi.mock('./useCategories', () => ({
  useCategory: () => ({ category: { id: 1, name: 'Test deck' }, ready: true, missing: false, error: null }),
}))

type TransactionEvent = Parameters<NonNullable<Sentry.BrowserOptions['beforeSendTransaction']>>[0]
const transactions: TransactionEvent[] = []
const renderedAtEnd: string[] = []
let host: HTMLDivElement

beforeEach(() => {
  transactions.length = 0
  renderedAtEnd.length = 0
  host = document.createElement('div')
  document.body.append(host)
  Sentry.init({
    dsn: 'https://public@example.com/1',
    traceLifecycle: 'static',
    tracesSampleRate: 1,
    defaultIntegrations: false,
    beforeSendTransaction(event) {
      transactions.push(event)
      renderedAtEnd.push(host.textContent ?? '')
      return event
    },
    transport: () => ({ send: async () => ({}), flush: async () => true }),
  })
})

afterEach(async () => {
  await act(() => render(null, host))
  host.remove()
  await Sentry.close()
  vi.unstubAllGlobals()
})

it('finishes only after the first card is committed to the DOM', async () => {
  let resolveResponse!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { resolveResponse = resolve })))
  await act(() => render(h(Study, { categoryId: 1, difficulties: ['beginner'] }), host))
  expect(transactions).toHaveLength(0)
  await act(async () => {
    resolveResponse(new Response(JSON.stringify({
      category: { id: 1, name: 'Test deck' }, difficulties: ['beginner'], total: 1,
      cards: [{ word_id: 1, mode: 'pinyin_to_english',
        answer_chinese: 'private-content', answer_pinyin: 'pinyin', answer_english: 'answer',
        example_chinese: '', example_pinyin: '', example_english: '' }],
    })))
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  await Sentry.flush()
  expect(transactions).toHaveLength(1)
  expect(transactions[0].contexts?.trace?.data?.['study.outcome']).toBe('ready')
  expect(JSON.stringify(transactions)).not.toContain('private-content')
})

it('marks failed session creation as a failure', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 500 })))
  await act(async () => {
    render(h(Study, { categoryId: 1, difficulties: ['beginner'] }), host)
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  await Sentry.flush()
  expect(transactions).toHaveLength(1)
  expect(transactions[0].contexts?.trace?.data?.['study.outcome']).toBe('failed')
  expect(transactions[0].contexts?.trace?.status).toBe('internal_error')
})
