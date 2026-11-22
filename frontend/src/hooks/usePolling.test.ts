import { renderHook } from '@testing-library/react'
import { usePolling } from './usePolling'

describe('usePolling', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('calls the function every interval while active, and stops when it is not', () => {
    const tick = vi.fn()
    const { rerender } = renderHook(({ active }) => usePolling(tick, active, 1000), { initialProps: { active: true } })

    vi.advanceTimersByTime(3500)
    expect(tick).toHaveBeenCalledTimes(3)

    rerender({ active: false })
    vi.advanceTimersByTime(5000)
    expect(tick).toHaveBeenCalledTimes(3)
  })

  it('never calls it when it starts inactive, and cleans up when it is removed', () => {
    const tick = vi.fn()
    const idle = renderHook(() => usePolling(tick, false, 1000))
    vi.advanceTimersByTime(3000)
    expect(tick).not.toHaveBeenCalled()
    idle.unmount()

    const busy = renderHook(() => usePolling(tick, true, 1000))
    busy.unmount()
    vi.advanceTimersByTime(3000)
    expect(tick).not.toHaveBeenCalled()
  })
})
