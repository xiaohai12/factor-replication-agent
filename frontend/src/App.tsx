import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AppLayout } from "@/layout/AppLayout"
import { ErrorBoundary } from "@/components/ErrorBoundary"
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
              <Route path="/extract" element={<ErrorBoundary><ExtractorPage /></ErrorBoundary>} />
              <Route path="/review" element={<ErrorBoundary><ReviewResolvePage /></ErrorBoundary>} />
              <Route path="/backtest" element={<ErrorBoundary><BacktestExperimentsPage /></ErrorBoundary>} />
              <Route path="/trace" element={<ErrorBoundary><TraceLogsPage /></ErrorBoundary>} />
              <Route path="/runs" element={<ErrorBoundary><RunsPage /></ErrorBoundary>} />
              <Route path="/runs/:sessionId/step/:step" element={<ErrorBoundary><SessionDetailPage /></ErrorBoundary>} />
              <Route path="/schema" element={<ErrorBoundary><SchemaReferencePage /></ErrorBoundary>} />
              <Route path="/data-catalog" element={<ErrorBoundary><DataCatalogPage /></ErrorBoundary>} />
            </Route>
          </Routes>
        </BrowserRouter>
      </LlmProvider>
    </QueryClientProvider>
  )
}

export default App
