import Icon from './Icon'

/**
 * Choose a text file. The browser's own "Choose file" control is hidden and a button stands in for it: the real input
 * stays in the page (hidden visually), so the keyboard and screen readers still work, and the button shows the focus
 * ring when it is tabbed to.
 */
export default function FileButton({
  label = 'Load a text file',
  hint = '.txt or .md',
  fileName,
  onFile,
}: {
  label?: string
  hint?: string
  /** The file that was loaded, shown beside the button. */
  fileName?: string | null
  onFile: (file: File) => void
}) {
  return (
    <div className="file-button">
      <label className="file-pick">
        <input
          type="file"
          className="sr-only"
          accept=".txt,.md,text/plain,text/markdown"
          onChange={(event) => {
            const file = event.target.files?.[0]
            event.target.value = '' // so choosing the same file again still counts as a change
            if (file) onFile(file)
          }}
        />
        <Icon name="upload" size={16} />
        {label}
      </label>
      <span className="meta">{fileName ? `Loaded ${fileName}` : hint}</span>
    </div>
  )
}
