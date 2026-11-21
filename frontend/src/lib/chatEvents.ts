// The chat list in the sidebar and the conversation on the page are separate parts of the screen. When a chat
// is created or used, the conversation says so with this event and the list reloads.

export const CHATS_CHANGED = 'cognipm:chats-changed'

export function notifyChatsChanged() {
  window.dispatchEvent(new Event(CHATS_CHANGED))
}

// The same for tasks: starting one, or one finishing, changes Super-Pilot's list.
export const RUNS_CHANGED = 'cognipm:runs-changed'

export function notifyRunsChanged() {
  window.dispatchEvent(new Event(RUNS_CHANGED))
}
