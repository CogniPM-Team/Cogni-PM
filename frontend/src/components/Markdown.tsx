import { Fragment } from 'react'
import { type Inline, parseMarkdown } from '../lib/markdown'

function Inlines({ parts }: { parts: Inline[] }) {
  return (
    <>
      {parts.map((part, index) => {
        switch (part.kind) {
          case 'bold':
            return <strong key={index}>{part.text}</strong>
          case 'italic':
            return <em key={index}>{part.text}</em>
          case 'code':
            return (
              <code key={index} className="mono">
                {part.text}
              </code>
            )
          default:
            return <Fragment key={index}>{part.text}</Fragment>
        }
      })}
    </>
  )
}

/** The model's answer with its formatting: bold stands out, lists are lists. Text is escaped by React, never injected as HTML. */
export default function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown">
      {parseMarkdown(text).map((block, index) => {
        if (block.kind === 'paragraph') {
          return (
            <p key={index}>
              {block.lines.map((line, i) => (
                <Fragment key={i}>
                  {i > 0 && <br />}
                  <Inlines parts={line} />
                </Fragment>
              ))}
            </p>
          )
        }
        const List = block.kind === 'bullets' ? 'ul' : 'ol'
        return (
          <List key={index}>
            {block.items.map((item, i) => (
              <li key={i}>
                <Inlines parts={item} />
              </li>
            ))}
          </List>
        )
      })}
    </div>
  )
}
