import { Link, Route, Routes } from 'react-router-dom'
import { AgentsPage } from './pages/AgentsPage'
import { AuditPage } from './pages/AuditPage'
import { ClaimDetailPage } from './pages/ClaimDetailPage'
import { ClaimsPage } from './pages/ClaimsPage'
import { ComparePage } from './pages/ComparePage'
import { RunDetailPage } from './pages/RunDetailPage'

function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <nav className="flex items-center gap-4 border-b border-slate-200 bg-white px-6 py-3 text-sm">
        <Link to="/" className="text-base font-semibold">
          Agentic Claims POC
        </Link>
        <span className="text-slate-300">|</span>
        <Link to="/" className="hover:underline">
          Claims
        </Link>
        <Link to="/audit" className="hover:underline">
          Audit
        </Link>
        <Link to="/agents" className="hover:underline">
          Agents
        </Link>
      </nav>
      <main className="mx-auto max-w-5xl p-6">
        <Routes>
          <Route path="/" element={<ClaimsPage />} />
          <Route path="/claims/:claimId" element={<ClaimDetailPage />} />
          <Route path="/claims/:claimId/runs/:correlationId" element={<RunDetailPage />} />
          <Route path="/claims/:claimId/compare/:a/:b" element={<ComparePage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/agents" element={<AgentsPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
