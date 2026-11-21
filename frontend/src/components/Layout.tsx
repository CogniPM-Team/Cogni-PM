import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import type { Project, RunList } from '../api/types'
import { useFetch } from '../api/useFetch'

function pageTitle(pathname: string): { title: string; crumb: string } {
  if (pathname.startsWith('/approvals/')) return { title: 'Review a run', crumb: 'Approvals › Review' }
  if (pathname.startsWith('/console')) return { title: 'Agent console', crumb: 'Agent console' }
  const titles: Record<string, string> = {
    '/console': 'Agent console',
    '/approvals': 'Approvals',
    '/activity': 'Activity log',
  }
  const title = titles[pathname] ?? 'CogniPM'
  return { title, crumb: title }
}

export default function Layout() {
  const { pathname } = useLocation()
  // The query string only makes the badge refetch on every navigation; the API ignores it.
  const { data: runs } = useFetch<RunList>(`/api/runs?page=${encodeURIComponent(pathname)}`)
  const { data: project } = useFetch<Project>('/api/project')
  const { title, crumb } = pageTitle(pathname)
  const waiting = runs?.awaiting_review_count ?? 0

  return (
    <div className="app">
      <aside className="sidebar">
        <Link className="project" to="/console" aria-label="CogniPM home">
          <span className="project-card">
            <img src="/cognipm-wordmark.png" alt="CogniPM" />
            <span className="project-sub">Jira · {project?.key ?? 'not connected'}</span>
          </span>
        </Link>

        <div className="side-scroll">
          <nav className="side-nav" aria-label="Main">
            <NavLink to="/console" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
              Agent console
            </NavLink>
            <NavLink to="/approvals" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
              Approvals
              {waiting > 0 && (
                <span className="nav-badge" aria-label={`${waiting} waiting for you`}>
                  {waiting}
                </span>
              )}
            </NavLink>
            <NavLink to="/activity" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
              Activity log
            </NavLink>
          </nav>
        </div>

        <div className="jira-card">
          <span>
            <span className={`jira-dot${project ? '' : ' off'}`} />
            {project ? 'Jira site' : 'Jira not connected'}
          </span>
          {project && <span className="jira-site">{project.jira_host}</span>}
        </div>
      </aside>

      <div className="main-col">
        <header className="topbar">
          <div>
            <p className="crumb">
              {project?.key}
              {project && ' › '}
              {crumb}
            </p>
            <h1>{title}</h1>
          </div>
          {project && (
            <a className="button-link" href={project.jira_url} target="_blank" rel="noopener noreferrer">
              Open in Jira
            </a>
          )}
        </header>
        <main>
          <div className="page">
            <Outlet />
          </div>
        </main>
        <footer className="site-footer">
          CogniPM is a research prototype. Agents can make mistakes: drafts, reasoning and chat answers may be
          inaccurate, and nothing is created in Jira until a person approves it. Check before you approve.
        </footer>
      </div>
    </div>
  )
}
