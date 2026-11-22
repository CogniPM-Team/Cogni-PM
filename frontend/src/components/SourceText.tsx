import type { Draft } from '../api/types'
import { segments } from '../lib/spans'

interface Props {
  text: string
  drafts: Pick<Draft, 'id' | 'sources'>[]
  /** The draft the reviewer is looking at: its quotes stand out from the others. */
  activeDraft: string | null
}

/** The original input with every cited quote highlighted in place, so a reviewer can see what each draft rests on. */
export default function SourceText({ text, drafts, activeDraft }: Props) {
  return (
    <p className="source-text">
      {segments(text, drafts).map((piece, index) =>
        piece.drafts.length === 0 ? (
          piece.text
        ) : (
          <mark key={index} className={activeDraft && piece.drafts.includes(activeDraft) ? 'active' : undefined}>
            {piece.text}
          </mark>
        ),
      )}
    </p>
  )
}
