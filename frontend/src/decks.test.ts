import { h, render } from 'preact'
import { act } from 'preact/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { Category } from './api'
import { Decks } from './decks'

const auth = vi.hoisted(() => ({ offline: false }))
const catalog = vi.hoisted(() => ({ categories: [] as Category[] }))

vi.mock('./auth', () => ({
  useAuth: () => ({
    offline: auth.offline,
    retryConnection: async () => false
  })
}))

vi.mock('./useCategories', () => ({
  useCategories: () => ({
    categories: catalog.categories,
    error: null
  })
}))

vi.mock('./useLearnerScore', () => ({
  useLearnerScore: () => ({ snapshot: null })
}))

let host: HTMLDivElement

function category (
  partial: Partial<Category> & Pick<Category, 'id' | 'name' | 'public'>
): Category {
  return {
    novice_count: 0,
    intermediate_count: 0,
    advanced_count: 0,
    expert_count: 0,
    last_practiced_at: null,
    ...partial
  }
}

function sectionLabels () {
  return [...host.querySelectorAll('.deck-section h2')].map(
    (heading) => heading.textContent
  )
}

beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  auth.offline = false
  catalog.categories = []
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

it('puts the learner decks between recent and all decks', async () => {
  catalog.categories = [
    category({
      id: 1,
      name: 'Food, Cooking & Dining',
      public: true,
      last_practiced_at: '2026-03-01T00:00:00Z'
    }),
    category({
      id: 2,
      name: 'Parents',
      public: false,
      last_practiced_at: '2026-04-01T00:00:00Z'
    }),
    category({ id: 3, name: 'Travel', public: true })
  ]
  await mount()
  expect(sectionLabels()).toEqual(['Recent', 'Custom decks', 'All decks'])
  const custom = host.querySelector('.custom-decks')
  expect(custom?.textContent).toContain('Parents')
  expect(custom?.textContent).not.toContain('Food, Cooking & Dining')
  expect(custom?.textContent).not.toContain('Travel')
  expect(custom?.lastElementChild?.textContent).toBe('+ Build new deck')
  const recent = [...host.querySelectorAll('.deck-section')].find(
    (section) => section.querySelector('h2')?.textContent === 'Recent'
  )
  expect(recent?.textContent).toContain('Food, Cooking & Dining')
  expect(recent?.textContent).not.toContain('Parents')
  const all = [...host.querySelectorAll('.deck-section')].find(
    (section) => section.querySelector('h2')?.textContent === 'All decks'
  )
  expect(all?.textContent).toContain('Food, Cooking & Dining')
  expect(all?.textContent).toContain('Travel')
  expect(all?.textContent).not.toContain('Parents')
})

it('keeps a matching learner deck in custom decks while searching', async () => {
  catalog.categories = [
    category({ id: 1, name: 'Food, Cooking & Dining', public: true }),
    category({ id: 2, name: 'Parents', public: false })
  ]
  await mount()
  const input = host.querySelector<HTMLInputElement>('input[name="deck-search"]')
  await act(() => {
    input!.value = 'Parents'
    input!.dispatchEvent(new Event('input', { bubbles: true }))
  })
  expect(host.querySelector('[aria-label="Decks"]')).toBeNull()
  expect(host.textContent).not.toContain('No decks match.')
  const custom = host.querySelector('.custom-decks')
  expect(custom?.textContent).toContain('Parents')
  expect(custom?.lastElementChild?.textContent).toBe('+ Build new deck')
})

it('shows a cached learner deck without the build button while offline', async () => {
  auth.offline = true
  catalog.categories = [
    category({ id: 1, name: 'Food, Cooking & Dining', public: true }),
    category({ id: 2, name: 'Parents', public: false })
  ]
  await mount()
  expect(sectionLabels()).toEqual(['Custom decks', 'Decks'])
  expect(host.querySelector('button.build-deck')).toBeNull()
  const decks = [...host.querySelectorAll('.deck-section')].find(
    (section) => section.querySelector('h2')?.textContent === 'Decks'
  )
  expect(decks?.textContent).toContain('Food, Cooking & Dining')
  expect(decks?.textContent).not.toContain('Parents')
  expect(host.querySelector('.custom-decks')?.textContent).toContain('Parents')
})

it('does not offer Build new deck while offline', async () => {
  auth.offline = true
  await mount()
  expect(host.querySelector('.custom-decks')).toBeNull()
  expect(host.querySelector('button.build-deck')).toBeNull()
  expect(host.textContent).toContain('Offline · progress not saved.')
  expect(window.location.pathname).toBe('/')
})
