const MONTH_MAP: Record<string, number> = {
  Jan: 0, Feb: 1, Mar: 2, Apr: 3, May: 4, Jun: 5,
  Jul: 6, Aug: 7, Sep: 8, Oct: 9, Nov: 10, Dec: 11,
}

export function parseNSEDate(dateStr: string): Date {
  // Handles "21-Nov-2024" format from NSE
  const parts = dateStr.split('-')
  if (parts.length === 3) {
    const day = parseInt(parts[0], 10)
    const month = MONTH_MAP[parts[1]] ?? 0
    const year = parseInt(parts[2], 10)
    return new Date(year, month, day)
  }
  return new Date(dateStr)
}

export function isLastThursdayOfMonth(date: Date): boolean {
  if (date.getDay() !== 4) return false   // 4 = Thursday
  // Check if adding 7 days goes to the next month
  const nextWeek = new Date(date)
  nextWeek.setDate(date.getDate() + 7)
  return nextWeek.getMonth() !== date.getMonth()
}

export function classifyExpiries(expiries: string[]): { weekly: string[]; monthly: string[] } {
  const weekly: string[] = []
  const monthly: string[] = []
  for (const e of expiries) {
    const d = parseNSEDate(e)
    if (isLastThursdayOfMonth(d)) {
      monthly.push(e)
    } else {
      weekly.push(e)
    }
  }
  return { weekly, monthly }
}
