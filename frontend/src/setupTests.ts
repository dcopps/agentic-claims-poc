import '@testing-library/jest-dom/vitest'

// jsdom has no EventSource; stub a no-op so components that open an SSE stream
// (via useRunStream) render in tests without a live connection.
class MockEventSource {
  url: string
  constructor(url: string) {
    this.url = url
  }
  addEventListener(): void {}
  removeEventListener(): void {}
  close(): void {}
}

;(globalThis as unknown as { EventSource: unknown }).EventSource = MockEventSource
