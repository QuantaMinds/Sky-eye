import axios from "axios"
import { getApiBaseUrl } from "@/lib/env"
import type {
  BatchAcceptResponse,
  BatchStatusResponse,
  BatchSubmitRequest,
} from "@/types/batch"

const client = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 30_000,
})

export async function submitBatch(
  req: BatchSubmitRequest
): Promise<BatchAcceptResponse> {
  const { data } = await client.post<BatchAcceptResponse>(
    "/api/v1/batch-score",
    req
  )
  return data
}

export async function getBatchStatus(jobId: string): Promise<BatchStatusResponse> {
  const { data } = await client.get<BatchStatusResponse>(
    `/api/v1/batch-score/${encodeURIComponent(jobId)}`
  )
  return data
}
