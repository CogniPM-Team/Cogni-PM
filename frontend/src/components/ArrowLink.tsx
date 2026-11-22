import type { MouseEventHandler, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import Icon from './Icon'

/**
 * A link that goes somewhere else in the app, drawn as a quiet label with an arrow instead of an underlined phrase.
 * `back` puts a left arrow in front: for "Back" and "Back to ...".
 */
export default function ArrowLink({
  to,
  children,
  back = false,
  onClick,
}: {
  to: string
  children: ReactNode
  back?: boolean
  onClick?: MouseEventHandler<HTMLAnchorElement>
}) {
  return (
    <Link to={to} className={`link-arrow${back ? ' back' : ''}`} onClick={onClick}>
      {back && <Icon name="back" size={16} />}
      {children}
      {!back && <Icon name="arrow" size={16} />}
    </Link>
  )
}
