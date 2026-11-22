// A small Markdown reader for the model's chat answers: paragraphs, bullet and numbered lists, **bold**,
// *italic* and `code`. It produces plain data, never HTML, so nothing the model writes can inject markup:
// the component turns these pieces into React elements, which escape their text.

export type Inline = { kind: 'text' | 'bold' | 'italic' | 'code'; text: string }

export type Block =
  | { kind: 'paragraph'; lines: Inline[][] }
  | { kind: 'bullets' | 'numbers'; items: Inline[][] }

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/

export function parseInline(text: string): Inline[] {
  return text
    .split(INLINE)
    .filter((part) => part !== '')
    .map((part): Inline => {
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) return { kind: 'bold', text: part.slice(2, -2) }
      if (part.startsWith('`') && part.endsWith('`') && part.length > 2) return { kind: 'code', text: part.slice(1, -1) }
      if ((part.startsWith('*') && part.endsWith('*')) || (part.startsWith('_') && part.endsWith('_'))) {
        if (part.length > 2) return { kind: 'italic', text: part.slice(1, -1) }
      }
      return { kind: 'text', text: part }
    })
}

const BULLET = /^\s*[*-]\s+(.*)$/
const NUMBER = /^\s*\d+[.)]\s+(.*)$/
const HEADING = /^\s*#{1,6}\s+(.*)$/

export function parseMarkdown(text: string): Block[] {
  const blocks: Block[] = []
  for (const raw of text.replaceAll('\r\n', '\n').split('\n')) {
    const bullet = BULLET.exec(raw)
    const number = NUMBER.exec(raw)
    const heading = HEADING.exec(raw)
    const last = blocks[blocks.length - 1]

    if (bullet || number) {
      const kind = bullet ? 'bullets' : 'numbers'
      const item = parseInline((bullet ?? number)![1])
      if (last && last.kind === kind) last.items.push(item)
      else blocks.push({ kind, items: [item] })
    } else if (raw.trim() === '') {
      blocks.push({ kind: 'paragraph', lines: [] }) // a blank line ends the current paragraph
    } else {
      const line = heading ? [{ kind: 'bold' as const, text: heading[1] }] : parseInline(raw.trim())
      if (last && last.kind === 'paragraph') last.lines.push(line)
      else blocks.push({ kind: 'paragraph', lines: [line] })
    }
  }
  return blocks.filter((block) => block.kind !== 'paragraph' || block.lines.length > 0)
}
