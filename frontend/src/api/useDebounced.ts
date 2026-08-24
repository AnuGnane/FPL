import { useEffect, useState } from 'react'

// One place for "wait until the typing stops". Every search box on the SPA
// drives a GET, so without this a five-letter name is five requests and the
// answers can land out of order. Lives next to useJob so all the request
// pacing is in one folder.
export function useDebounced<T>(value: T, delay = 250): T {
  const [settled, setSettled] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return settled
}
