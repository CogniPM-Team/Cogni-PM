import { parseInline, parseMarkdown } from './markdown'

describe('parseInline', () => {
  it('finds bold, italic and code, and leaves other text alone', () => {
    expect(parseInline('There are **0** issues with `Task` type, *really*')).toEqual([
      { kind: 'text', text: 'There are ' },
      { kind: 'bold', text: '0' },
      { kind: 'text', text: ' issues with ' },
      { kind: 'code', text: 'Task' },
      { kind: 'text', text: ' type, ' },
      { kind: 'italic', text: 'really' },
    ])
    expect(parseInline('2 * 3 = 6')).toEqual([{ kind: 'text', text: '2 * 3 = 6' }])
  })
})

describe('parseMarkdown', () => {
  it('turns the answer from the screenshot into paragraphs and a bullet list with bold labels', () => {
    const blocks = parseMarkdown(
      'There are **0** issues with the type **Task**.\n\nFor reference, the breakdown is:\n* **Stories:** 12\n* **Sub-tasks:** 2\n* **Epic:** 1',
    )

    expect(blocks.map((b) => b.kind)).toEqual(['paragraph', 'paragraph', 'bullets'])
    const list = blocks[2]
    expect(list.kind === 'bullets' && list.items).toHaveLength(3)
    expect(list.kind === 'bullets' && list.items[0]).toEqual([
      { kind: 'bold', text: 'Stories:' },
      { kind: 'text', text: ' 12' },
    ])
  })

  it('handles numbered lists, dashes, headings, and line breaks inside a paragraph', () => {
    const blocks = parseMarkdown('## Summary\nline two\n\n1. first\n2) second\n- dash')

    expect(blocks[0]).toEqual({
      kind: 'paragraph',
      lines: [[{ kind: 'bold', text: 'Summary' }], [{ kind: 'text', text: 'line two' }]],
    })
    expect(blocks[1].kind === 'numbers' && blocks[1].items).toHaveLength(2)
    expect(blocks[2].kind).toBe('bullets')
  })

  it('treats markup as text, never as HTML', () => {
    const [block] = parseMarkdown('<img src=x onerror=alert(1)> **bold**')

    expect(block.kind === 'paragraph' && block.lines[0][0]).toEqual({
      kind: 'text',
      text: '<img src=x onerror=alert(1)> ',
    })
  })
})
