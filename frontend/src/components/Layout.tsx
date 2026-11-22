import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import type { Project, RunList } from '../api/types'
import { useFetch } from '../api/useFetch'
import { type NavItem, pageInfo, visibleNav } from '../lib/nav'

export default function Layout() {
  const { pathname } = useLocation()
  // The query string only makes the badge refetch on every navigation; the API ignores it.
  const { data: runs } = useFetch<RunList>(`/api/runs?page=${encodeURIComponent(pathname)}`)
  const { data: project } = useFetch<Project>('/api/project')
  const { title, crumb } = pageInfo(pathname)
  const waiting = runs?.awaiting_review_count ?? 0
  const groups = visibleNav()

  const renderItem = (item: NavItem) => (
    <NavLink key={item.id} to={item.path} className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
      {item.label}
      {item.badge === 'waiting' && waiting > 0 && (
        <span className="nav-badge" aria-label={`${waiting} waiting for you`}>
          {waiting}
        </span>
      )}
    </NavLink>
  )

  return (
    <div className="app">
      <aside className="sidebar">
        <Link className="project" to="/home" aria-label="CogniPM home">
          <span className="project-card">
            <img src="/cognipm-wordmark.png" alt="CogniPM" />
            <span className="project-sub">Jira · {project?.key ?? 'not connected'}</span>
          </span>
        </Link>

        <div className="side-scroll">
          <nav className="side-nav" aria-label="Main">
            {groups
              .filter((group) => group.section !== 'SYSTEM')
              .map((group) => (
                <div key={group.section} role="group" aria-label={group.section.toLowerCase()}>
                  <span className="nav-label" aria-hidden="true">
                    {group.section}
                  </span>
                  {group.items.map(renderItem)}
                </div>
              ))}
          </nav>
        </div>

        {/* Setup pages sit at the bottom, out of the scrolling list, so they are always in the same place. */}
        <nav className="side-nav side-foot" aria-label="System">
          {groups.filter((group) => group.section === 'SYSTEM').flatMap((group) => group.items.map(renderItem))}
        </nav>

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
          <div className={`page${pathname.startsWith('/console') ? ' wide' : ''}`}>
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
