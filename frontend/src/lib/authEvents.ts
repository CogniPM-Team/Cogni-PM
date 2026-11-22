/** Sent when the server says nobody is signed in any more (the session ran out, or it was ended elsewhere). */
export const SIGNED_OUT = 'cognipm:signed-out'

export function notifySignedOut() {
  window.dispatchEvent(new Event(SIGNED_OUT))
}
