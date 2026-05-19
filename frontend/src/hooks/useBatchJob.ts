import { useCallback, useEffect, useRef, useState } from "react"
import { getBatchStatus, submitBatch } from "@/lib/api-batch"
import type { BatchStatusResponse } from "@/types/batch"

export type BatchStage = "idle" | "submitting" | "polling" | "complete" | "error"

export interface UseBatchJobReturn {
  stage: BatchStage
  jobId: string | null
  status: BatchStatusResponse | null
  error: string | null
  submit: (addresses: string[]) => Promise<void>
  reset: () => void
}

// Backoff in ms: start tight (UI feels responsive on small jobs), widen
// out for long-running large batches so we don't hammer the API.
const POLL_INTERVALS_MS = [1000, 1000, 2000, 4000, 8000]

function nextDelay(pollIndex: number): number {
  return POLL_INTERVALS_MS[Math.min(pollIndex, POLL_INTERVALS_MS.length - 1)]
}

function errMsg(e: unknown): string {
  if (e instanceof Error) return e.message
  return typeof e === "string" ? e : "Unknown error"
}

export function useBatchJob(): UseBatchJobReturn {
  const [stage, setStage] = useState<BatchStage>("idle")
  const [jobId, setJobId] = useState<string | null>(null)
  const [status, setStatus] = useState<BatchStatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cancelledRef = useRef(false)

  const clearTimer = () => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  const reset = useCallback(() => {
    cancelledRef.current = true
    clearTimer()
    setStage("idle")
    setJobId(null)
    setStatus(null)
    setError(null)
  }, [])

  useEffect(() => () => {
    cancelledRef.current = true
    clearTimer()
  }, [])

  const pollOnce = useCallback(async (id: string, pollIndex: number) => {
    if (cancelledRef.current) return
    try {
      const next = await getBatchStatus(id)
      if (cancelledRef.current) return
      setStatus(next)
      if (next.status === "complete") {
        setStage("complete")
        return
      }
      timerRef.current = setTimeout(
        () => void pollOnce(id, pollIndex + 1),
        nextDelay(pollIndex)
      )
    } catch (e) {
      if (cancelledRef.current) return
      setError(errMsg(e))
      setStage("error")
    }
  }, [])

  const submit = useCallback(async (addresses: string[]) => {
    cancelledRef.current = false
    clearTimer()
    setError(null)
    setStatus(null)
    setStage("submitting")
    try {
      const accepted = await submitBatch({ addresses })
      if (cancelledRef.current) return
      setJobId(accepted.job_id)
      setStage("polling")
      void pollOnce(accepted.job_id, 0)
    } catch (e) {
      if (cancelledRef.current) return
      setError(errMsg(e))
      setStage("error")
    }
  }, [pollOnce])

  return { stage, jobId, status, error, submit, reset }
}
