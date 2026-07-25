import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AppLayout } from "@/layout/AppLayout"
import { LlmProvider } from "@/lib/llmContext"
import { PipelineE2EPage } from "@/pages/PipelineE2EPage"
import { BacktestExperimentsPage } from "@/pages/BacktestExperimentsPage"
import { TraceLogsPage } from "@/pages/TraceLogsPage"

const queryClient = new QueryClient()

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <LlmProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<Navigate to="/pipeline" replace />} />
              <Route path="/pipeline" element={<PipelineE2EPage />} />
              <Route path="/backtest" element={<BacktestExperimentsPage />} />
              <Route path="/trace" element={<TraceLogsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </LlmProvider>
    </QueryClientProvider>
  )
}

export default App
