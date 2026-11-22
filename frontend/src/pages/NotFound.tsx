import { Link } from 'react-router-dom'
import { EmptyState } from '../components/PageParts'

export default function NotFound() {
  return (
    <EmptyState title="Page not found" action={<Link to="/console">Go to the Agent console</Link>}>
      There is nothing at this address.
    </EmptyState>
  )
}
