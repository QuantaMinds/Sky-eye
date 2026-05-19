import { BrowserRouter, Route, Routes } from "react-router-dom"
import { Batch } from "@/pages/Batch"
import { Landing } from "@/pages/Landing"
import { ScoreResult } from "@/pages/ScoreResult"

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/batch" element={<Batch />} />
        <Route path="/score/:apn" element={<ScoreResult />} />
      </Routes>
    </BrowserRouter>
  )
}
