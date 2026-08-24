import { useEffect, useState } from 'react'

function remaining(deadline: string): string {
  const ms = new Date(deadline).getTime() - Date.now()
  if (ms <= 0) return 'deadline passed'
  const minutes = Math.floor(ms / 60000)
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  return `${days}d ${hours}h ${minutes % 60}m to deadline`
}

export default function Countdown({ deadline }: { deadline: string }) {
  const [label, setLabel] = useState(() => remaining(deadline))
  useEffect(() => {
    setLabel(remaining(deadline))
    const timer = window.setInterval(
      () => setLabel(remaining(deadline)), 30000)
    return () => window.clearInterval(timer)
  }, [deadline])
  return <span className="muted">{label}</span>
}
