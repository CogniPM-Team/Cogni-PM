import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Activity from './pages/Activity'
import AgentConsole from './pages/AgentConsole'
import Approvals from './pages/Approvals'
import NotFound from './pages/NotFound'
import RunReview from './pages/RunReview'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/console" replace />} />
        <Route path="console/:chatId?" element={<AgentConsole />} />
        <Route path="approvals" element={<Approvals />} />
        <Route path="approvals/:id" element={<RunReview />} />
        <Route path="activity" element={<Activity />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
