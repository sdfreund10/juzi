import { h, render } from 'preact'
import { act } from 'preact/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { DeckNew } from './deckNew'

const clearUser = vi.hoisted(() => vi.fn())

vi.mock('./auth', () => ({
  useAuth: () => ({
    clearUser
  })
}))

function json (body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' }
  })
}

let host: HTMLDivElement

beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  window.history.replaceState(null, '', '/decks/new')
  clearUser.mockReset()
})

afterEach(async () => {
  await act(() => render(null, host))
  host.remove()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function mount () {
  await act(() => render(h(DeckNew, {}), host))
}

function promptInput () {
  const input = host.querySelector<HTMLTextAreaElement>('textarea[name="prompt"]')
  expect(input).not.toBeNull()
  return input!
}

async function typePrompt (value: string) {
  const input = promptInput()
  input.value = value
  await act(() => {
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

async function chooseSize (size: number) {
  const input = host.querySelector<HTMLInputElement>(`input[name="size"][value="${size}"]`)
  expect(input).not.toBeNull()
  await act(() => {
    input!.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

async function flush () {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

async function submit () {
  const form = host.querySelector('form')
  expect(form).not.toBeNull()
  await act(async () => {
    form!.requestSubmit()
  })
  await flush()
}

it('grows the prompt field with the text', async () => {
  await mount()
  const field = promptInput()
  expect(field.tagName).toBe('TEXTAREA')
  expect(Number(field.rows)).toBe(1)
  await typePrompt('line one\nline two\nline three')
  expect(field.value).toBe('line one\nline two\nline three')
})

it('starts with size 40 selected', async () => {
  await mount()
  const selected = host.querySelector<HTMLInputElement>('input[name="size"]:checked')
  expect(selected?.value).toBe('40')
})

it('submits the chosen size and the trimmed prompt', async () => {
  const fetchMock = vi.fn(async () => json({ id: 9, name: 'Parents' }, 201))
  vi.stubGlobal('fetch', fetchMock)
  const replace = vi.spyOn(window.history, 'replaceState')
  const push = vi.spyOn(window.history, 'pushState')
  await mount()
  await typePrompt('  tea with family  ')
  await chooseSize(60)
  await submit()

  expect(fetchMock).toHaveBeenCalledWith('/api/decks/', expect.objectContaining({
    method: 'POST',
    credentials: 'same-origin',
    body: JSON.stringify({ prompt: 'tea with family', size: 60 })
  }))
  expect(replace).toHaveBeenCalledWith(null, '', '/category/9/sessions/new')
  expect(push).not.toHaveBeenCalled()
  expect(window.location.pathname).toBe('/category/9/sessions/new')
})

it('does not submit an empty prompt', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  await mount()
  await submit()
  await typePrompt('   ')
  await submit()
  expect(fetchMock).not.toHaveBeenCalled()
})

it('keeps the prompt when no words match', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => json({ detail: 'No matching words.' }, 422)))
  await mount()
  await typePrompt('nothing close')
  await chooseSize(20)
  await submit()

  expect(promptInput().value).toBe('nothing close')
  expect(host.textContent).toContain('No matching words.')
  expect(window.location.pathname).toBe('/decks/new')
  expect(host.querySelector('button.cta')?.hasAttribute('disabled')).toBe(false)
  const selected = host.querySelector<HTMLInputElement>('input[name="size"]:checked')
  expect(selected?.value).toBe('20')
})

it('shows the retry sentence when the build fails', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => json({ detail: 'Could not build a deck. Try again.' }, 503)))
  await mount()
  await typePrompt('tea')
  await submit()
  expect(host.textContent).toContain('Could not build a deck. Try again.')
  expect(promptInput().value).toBe('tea')
  expect(window.location.pathname).toBe('/decks/new')
})

it('shows the retry sentence when the network fails', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => {
    throw new TypeError('offline')
  }))
  await mount()
  await typePrompt('tea')
  await submit()
  expect(host.textContent).toContain('Could not build a deck. Try again.')
  expect(window.location.pathname).toBe('/decks/new')
})

it('signs out on 401', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => json({ detail: 'Authentication credentials were not provided.' }, 401)))
  await mount()
  await typePrompt('tea')
  await submit()
  expect(clearUser).toHaveBeenCalledOnce()
  expect(window.location.pathname).toBe('/decks/new')
})

it('disables Build and shows Choosing words while the request is in flight', async () => {
  let release: (response: Response) => void = () => {}
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => {
    release = resolve
  })))
  const replace = vi.spyOn(window.history, 'replaceState')
  await mount()
  await typePrompt('tea')
  await submit()

  const build = host.querySelector<HTMLButtonElement>('button.cta')
  expect(build?.disabled).toBe(true)
  expect(promptInput().disabled).toBe(true)
  expect(host.textContent).toContain('Choosing words…')

  await act(async () => {
    release(json({ id: 4, name: 'Tea' }, 201))
  })
  await flush()
  expect(replace).toHaveBeenCalledWith(null, '', '/category/4/sessions/new')
})
