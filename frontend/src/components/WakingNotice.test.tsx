import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { noticeCopy } from '../copy/notices'
import { WakingNotice } from './WakingNotice'

// Prompt 29 (Dermot, 12 November 2026): one shared notice for the wait a
// visitor would otherwise have to guess at, shown only once a request has
// waited more than three seconds, gone the moment it is answered.
describe('WakingNotice', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('says nothing for the first three seconds, then says the server is waking', () => {
    render(<WakingNotice waiting />)
    act(() => vi.advanceTimersByTime(2999))
    expect(screen.queryByTestId('waking-notice')).not.toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1))
    expect(screen.getByRole('status')).toHaveTextContent(
      'Waking the server. After a quiet period this takes up to half a minute.',
    )
    expect(screen.getByRole('status')).toHaveTextContent(noticeCopy.waking)
  })

  it('disappears when the data arrives', () => {
    const { rerender } = render(<WakingNotice waiting />)
    act(() => vi.advanceTimersByTime(3000))
    expect(screen.getByTestId('waking-notice')).toBeInTheDocument()
    rerender(<WakingNotice waiting={false} />)
    expect(screen.queryByTestId('waking-notice')).not.toBeInTheDocument()
  })

  it('never appears for a request answered within three seconds, and counts afresh next time', () => {
    const { rerender } = render(<WakingNotice waiting />)
    act(() => vi.advanceTimersByTime(2000))
    rerender(<WakingNotice waiting={false} />)
    act(() => vi.advanceTimersByTime(5000))
    expect(screen.queryByTestId('waking-notice')).not.toBeInTheDocument()
    rerender(<WakingNotice waiting />)
    act(() => vi.advanceTimersByTime(2999))
    expect(screen.queryByTestId('waking-notice')).not.toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1))
    expect(screen.getByTestId('waking-notice')).toBeInTheDocument()
  })

  it('is absent when nothing is waiting', () => {
    render(<WakingNotice waiting={false} />)
    act(() => vi.advanceTimersByTime(10000))
    expect(screen.queryByTestId('waking-notice')).not.toBeInTheDocument()
  })
})
