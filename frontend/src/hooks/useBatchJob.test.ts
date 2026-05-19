import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { BatchAcceptResponse, BatchStatusResponse } from "@/types/batch"

vi.mock("@/lib/api-batch", () => ({
  submitBatch: vi.fn(),
  getBatchStatus: vi.fn(),
}))

import { useBatchJob } from "@/hooks/useBatchJob"
import * as api from "@/lib/api-batch"

const mockedSubmit = vi.mocked(api.submitBatch)
const mockedStatus = vi.mocked(api.getBatchStatus)

const accepted: BatchAcceptResponse = {
  job_id: "job-123",
  status: "queued",
  address_count: 3,
}

function makeStatus(
  s: BatchStatusResponse["status"],
  extras: Partial<BatchStatusResponse> = {},
): BatchStatusResponse {
  return {
    job_id: "job-123",
    status: s,
    address_count: 3,
    completed_count: 0,
    skipped_count: 0,
    failed_count: 0,
    results: [],
    ...extras,
  }
}

beforeEach(() => {
  mockedSubmit.mockReset()
  mockedStatus.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe("useBatchJob", () => {
  it("submit -> polling -> complete drives stage transitions (real timers, complete on first poll)", async () => {
    // Real timers: the first poll fires immediately (no setTimeout), so the
    // happy path needs no time advancement. Using waitFor here lets the
    // microtask chain (submit -> pollOnce -> setStage) settle.
    mockedSubmit.mockResolvedValue(accepted)
    mockedStatus.mockResolvedValueOnce(
      makeStatus("complete", { completed_count: 2, skipped_count: 1 }),
    )

    const { result } = renderHook(() => useBatchJob())
    expect(result.current.stage).toBe("idle")

    await act(async () => {
      await result.current.submit(["1 A St", "2 B St", "3 C St"])
    })
    expect(result.current.jobId).toBe("job-123")

    await waitFor(() => expect(result.current.stage).toBe("complete"))
    expect(result.current.status?.completed_count).toBe(2)
    expect(result.current.status?.skipped_count).toBe(1)
    expect(mockedStatus).toHaveBeenCalledTimes(1)
  })

  it("submit error sets stage=error with the error message", async () => {
    mockedSubmit.mockRejectedValue(new Error("network down"))
    const { result } = renderHook(() => useBatchJob())
    await act(async () => {
      await result.current.submit(["1 A St"])
    })
    expect(result.current.stage).toBe("error")
    expect(result.current.error).toBe("network down")
  })

  it("reset returns to idle and stops further polls", async () => {
    // Fake timers here because we need to assert "no more poll calls after
    // reset". With real timers, the 1s setTimeout would fire and add noise.
    vi.useFakeTimers()
    mockedSubmit.mockResolvedValue(accepted)
    mockedStatus.mockResolvedValue(makeStatus("processing"))

    const { result } = renderHook(() => useBatchJob())
    await act(async () => {
      await result.current.submit(["1 A St"])
    })
    // Drain the immediate first poll.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.stage).toBe("polling")
    const callsBefore = mockedStatus.mock.calls.length

    act(() => result.current.reset())
    expect(result.current.stage).toBe("idle")
    expect(result.current.jobId).toBeNull()

    // Advance past the next scheduled poll — must not fire.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })
    expect(mockedStatus.mock.calls.length).toBe(callsBefore)
  })
})
