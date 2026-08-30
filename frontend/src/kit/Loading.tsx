import Card from './Card'

export interface LoadingProps {
  /** What is being waited on, when the page can say something useful. */
  label?: string
}

/**
 * The one loading state.
 *
 * A bare "Loading…" floating on the page background was the single most
 * common way a hub broke the card rhythm: the panel that is about to appear
 * has a frame, and the wait for it should occupy the same frame rather than
 * collapsing the layout and pushing everything up when the data lands.
 */
export default function Loading({ label = 'Loading…' }: LoadingProps) {
  return (
    <Card>
      <p className="text-text-muted">{label}</p>
    </Card>
  )
}
