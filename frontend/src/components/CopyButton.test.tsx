import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { CopyButton } from "@/components/CopyButton"

describe("<CopyButton>", () => {
  it("calls clipboard.writeText with the given text on click", async () => {
    const user = userEvent.setup()
    const spy = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined)
    render(<CopyButton text="7076-019-008" />)
    await user.click(screen.getByTestId("copy-button"))
    expect(spy).toHaveBeenCalledWith("7076-019-008")
  })

  it("flips data-copied to true after a successful copy", async () => {
    const user = userEvent.setup()
    vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined)
    render(<CopyButton text="abc" />)
    const btn = screen.getByTestId("copy-button")
    await user.click(btn)
    await waitFor(() => expect(btn).toHaveAttribute("data-copied", "true"))
  })

  it("stays not-copied when clipboard rejects", async () => {
    const user = userEvent.setup()
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("denied"))
    render(<CopyButton text="abc" />)
    const btn = screen.getByTestId("copy-button")
    await user.click(btn)
    expect(btn).toHaveAttribute("data-copied", "false")
  })
})
