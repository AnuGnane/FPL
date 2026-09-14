import { useLayoutEffect, useRef } from 'react'

/**
 * Where focus goes when a modal closes.
 *
 * v18f §2.2. Radix's dialog returns focus to its own `Dialog.Trigger`, and
 * neither dialog in this app has one: every caller mounts the dialog beside
 * the control that opened it — a player's name in a table cell, a row's pin
 * button — and unmounts it on close. With no trigger to go back to, Radix
 * leaves focus on `document.body`, which for a keyboard reader is the top of
 * the page and no memory of which row he was on.
 *
 * So the element holding focus when the dialog mounts is remembered in a
 * layout effect — which runs before the focus scope's own effect moves it —
 * and handed back from `onCloseAutoFocus`, whose `preventDefault` is what
 * stops Radix reaching for the trigger that is not there.
 */
export default function useOpener(): (event: Event) => void {
  const opener = useRef<HTMLElement | null>(null)
  useLayoutEffect(() => {
    opener.current = document.activeElement as HTMLElement | null
  }, [])
  return (event: Event) => {
    event.preventDefault()
    opener.current?.focus()
  }
}
