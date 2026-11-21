import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <>
      <p className="empty">There is nothing at this address.</p>
      <Link to="/console">Go to the Agent console</Link>
    </>
  )
}
