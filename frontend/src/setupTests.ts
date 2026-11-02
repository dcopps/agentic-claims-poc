import '@testing-library/jest-dom/vitest'

// jsdom has no EventSource. This stub records the URL it was opened with and the
// listeners added, so a page renders without a live connection and a hook test
// can push frames in with `emit`. `latest()` returns the most recently opened
// instance; `closed` records that the hook's cleanup ran.
export class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  closed = false
  private listeners: Record<string, EventListener[]> = {}

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  static latest(): MockEventSource {
    const instance = MockEventSource.instances.at(-1)
    if (!instance) throw new Error('MockEventSource: nothing has opened a stream yet')
    return instance
  }

  addEventListener(name: string, listener: EventListener): void {
    ;(this.listeners[name] ??= []).push(listener)
  }

  removeEventListener(name: string, listener: EventListener): void {
    this.listeners[name] = (this.listeners[name] ?? []).filter((l) => l !== listener)
  }

  emit(name: string, data: string): void {
    for (const listener of this.listeners[name] ?? []) {
      listener(new MessageEvent(name, { data }))
    }
  }

  close(): void {
    this.closed = true
  }
}

;(globalThis as unknown as { EventSource: unknown }).EventSource = MockEventSource
