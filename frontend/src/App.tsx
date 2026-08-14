import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AppLayout } from "@/layout/AppLayout"
import { LlmProvider } from "@/lib/llmContext"
import { BacktestExperimentsPage } from "@/pages/BacktestExperimentsPage"
import { TraceLogsPage } from "@/pages/TraceLogsPage"
import { RunsPage } from "@/pages/RunsPage"
import { SessionDetailPage } from "@/pages/SessionDetailPage"
import { SchemaReferencePage } from "@/pages/SchemaReferencePage"
import { DataCatalogPage } from "@/pages/DataCatalogPage"
import { ExtractorPage } from "@/pages/ExtractorPage"
import { ReviewResolvePage } from "@/pages/ReviewResolvePage"

const queryClient = new QueryClient()

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <LlmProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<Navigate to="/runs" replace />} />
              <Route path="/extract" element={<ExtractorPage />} />
              <Route path="/review" element={<ReviewResolvePage />} />
              <Route path="/backtest" element={<BacktestExperimentsPage />} />
              <Route path="/trace" element={<TraceLogsPage />} />
              <Route path="/runs" element={<RunsPage />} />
              <Route path="/runs/:sessionId/step/:step" element={<SessionDetailPage />} />
              <Route path="/schema" element={<SchemaReferencePage />} />
              <Route path="/data-catalog" element={<DataCatalogPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </LlmProvider>
    </QueryClientProvider>
  )
}

export default App
