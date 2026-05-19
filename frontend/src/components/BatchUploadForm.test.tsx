import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { BatchUploadForm } from "@/components/BatchUploadForm"

describe("<BatchUploadForm>", () => {
  it("disables submit when no addresses are entered", () => {
    render(<BatchUploadForm onSubmit={vi.fn()} />)
    expect(screen.getByRole("button", { name: /score batch/i })).toBeDisabled()
  })

  it("counts addresses live and surfaces dedup count", async () => {
    const user = userEvent.setup()
    render(<BatchUploadForm onSubmit={vi.fn()} />)
    const ta = screen.getByLabelText(/paste addresses/i)
    await user.type(ta, "1 Main St\n2 Oak Ave\n1 MAIN ST")
    expect(screen.getByTestId("batch-upload-summary")).toHaveTextContent("2 addresses")
    expect(screen.getByTestId("batch-upload-summary")).toHaveTextContent("1 duplicate removed")
  })

  it("calls onSubmit with the parsed deduped list", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<BatchUploadForm onSubmit={onSubmit} />)
    await user.type(
      screen.getByLabelText(/paste addresses/i),
      "1 Main St\n2 Oak Ave"
    )
    await user.click(screen.getByRole("button", { name: /score batch/i }))
    expect(onSubmit).toHaveBeenCalledWith(["1 Main St", "2 Oak Ave"])
  })

  it("disables the whole form when disabled prop is true", () => {
    render(<BatchUploadForm onSubmit={vi.fn()} disabled />)
    expect(screen.getByLabelText(/paste addresses/i)).toBeDisabled()
    expect(screen.getByLabelText(/file upload/i)).toBeDisabled()
    expect(screen.getByRole("button", { name: /score batch/i })).toBeDisabled()
  })
})
