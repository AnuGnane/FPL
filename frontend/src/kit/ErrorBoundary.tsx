import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import Button from './Button'
import Callout from './Callout'

export interface ErrorBoundaryProps {
  children: ReactNode
  /** Changing this clears the caught error — the route path, in `App`. */
  resetKey?: string
}

interface ErrorBoundaryState {
  error: Error | null
}

/**
 * The last line between a TypeError during render and a white screen
 * (v18e §2.4).
 *
 * A class, because `componentDidCatch` has no hook equivalent and React
 * offers no other way to hear about a throw below you. React's answer to an
 * uncaught render error is to unmount the whole tree, so without this the
 * user gets a blank page and no way back; with it they get the message and a
 * reload, and the nav around it survives.
 *
 * Resets on `resetKey` because the error belongs to the page that threw:
 * navigating away is the user's own attempt to recover and must not be met
 * with the previous hub's stack trace.
 */
export default class ErrorBoundary
  extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // The one place the component stack is available at all; the browser
    // console is where a user is asked to look when reporting this.
    console.error('render error', error, info.componentStack)
  }

  componentDidUpdate(prev: ErrorBoundaryProps): void {
    if (prev.resetKey !== this.props.resetKey && this.state.error !== null) {
      this.setState({ error: null })
    }
  }

  render(): ReactNode {
    const { error } = this.state
    if (error === null) return this.props.children
    return (
      <Callout tone="error">
        {error.message}{' '}
        <Button variant="ghost" onClick={() => { window.location.reload() }}>
          Reload page
        </Button>
      </Callout>
    )
  }
}
