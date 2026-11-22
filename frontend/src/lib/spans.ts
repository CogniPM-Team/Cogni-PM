import type { Draft } from '../api/types'

export interface Segment {
  text: string
  /** The drafts whose cited quotes cover this stretch of the input; empty for plain text. */
  drafts: string[]
}

/**
 * Cuts the original input into pieces so each cited quote can be highlighted in place. A stretch cited by
 * two drafts carries both ids. Quotes the server could not locate (start is null) are skipped.
 */
export function segments(text: string, drafts: Pick<Draft, 'id' | 'sources'>[]): Segment[] {
  const ranges = drafts.flatMap((draft) =>
    draft.sources.flatMap((s) =>
      s.start !== null && s.end !== null && s.end > s.start ? [{ id: draft.id, start: s.start, end: s.end }] : [],
    ),
  )
  const cuts = [...new Set([0, text.length, ...ranges.flatMap((r) => [r.start, r.end])])]
    .filter((c) => c >= 0 && c <= text.length)
    .sort((a, b) => a - b)
  const pieces: Segment[] = []
  for (let i = 0; i < cuts.length - 1; i++) {
    const [from, to] = [cuts[i], cuts[i + 1]]
    pieces.push({
      text: text.slice(from, to),
      drafts: [...new Set(ranges.filter((r) => r.start <= from && r.end >= to).map((r) => r.id))],
    })
  }
  return pieces
}
