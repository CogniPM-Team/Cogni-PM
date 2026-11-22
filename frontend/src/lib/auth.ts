import { createContext, useContext } from 'react'
import type { User } from '../api/types'
import { actorLabel } from './format'

export interface Auth {
  /** Who is signed in; null only where there is no sign-in at all (tests, the sign-in page itself). */
  user: User | null
  /** A PM can change things; a developer can only look. The server decides for real: this is only so the page does not
   *  offer what would be refused. */
  canChange: boolean
  signOut: () => Promise<void>
}

export const AuthContext = createContext<Auth>({ user: null, canChange: true, signOut: async () => {} })

export const useAuth = () => useContext(AuthContext)

export const ROLE_NAMES: Record<User['role'], string> = { pm: 'PM', developer: 'Developer' }

/** `label(actor, name)` for a log entry: the person's name, "You" for yourself, an agent as an agent. */
export function useActorLabel() {
  const { user } = useAuth()
  return (actor: string, name?: string | null) => actorLabel(actor, { name, meId: user?.id })
}
