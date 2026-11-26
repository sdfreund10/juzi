import { h, render } from 'preact'
import { act } from 'preact/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Decks } from './decks'

const auth = vi.hoisted(() => ({ offline: false }))

vi.mock('./auth', () => ({
  useAuth: () => ({
    offline: auth.offline,
    retryConnection: async () => false
  })
}))

vi.mock('./useCategories', () => ({
  useCategories: () => ({
    categories: [],
    error: null
  })
}))

vi.mock('./useLearnerScore', () => ({
  useLearnerScore: () => ({ snapshot: null })
}))

let host: HTMLDivElement

beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  auth.offline = false
  window.history.replaceState(null, '', '/')
})

afterEach(async () => {
  await act(() => render(null, host))
  host.remove()
  vi.restoreAllMocks()
})

async function mount () {
  await act(() => render(h(Decks, {}), host))
}

it('opens the new deck form from the custom decks section', async () => {
  await mount()
  const section = host.querySelector('.custom-decks')
  expect(section?.textContent).toContain('Custom decks')
  const button = section?.querySelector<HTMLButtonElement>('button.build-deck')
  expect(button?.textContent).toBe('+ Build new deck')
  expect(host.querySelector('h1 + .build-deck')).toBeNull()
  expect(host.textContent).toContain('No decks yet. Seed vocabulary to get started.')
  await act(() => {
    button!.click()
  })
  expect(window.location.pathname).toBe('/decks/new')
})

it('does not offer Build new deck while offline', async () => {
  auth.offline = true
  await mount()
  expect(host.querySelector('.custom-decks')).toBeNull()
  expect(host.querySelector('button.build-deck')).toBeNull()
  expect(host.textContent).toContain('Offline · progress not saved.')
  expect(window.location.pathname).toBe('/')
})
