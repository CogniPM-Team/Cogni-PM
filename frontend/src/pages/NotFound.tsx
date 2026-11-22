import ArrowLink from '../components/ArrowLink'
import { EmptyState } from '../components/PageParts'

export default function NotFound() {
  return (
    <EmptyState title="Page not found" action={<ArrowLink to="/home">Go to Home</ArrowLink>}>
      There is nothing at this address.
    </EmptyState>
  )
}
