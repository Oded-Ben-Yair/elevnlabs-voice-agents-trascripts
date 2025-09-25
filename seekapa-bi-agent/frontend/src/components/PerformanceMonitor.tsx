import { useAppStore } from '../store'

// Performance thresholds
const THRESHOLDS = {
  FCP: { good: 1800, poor: 3000 },
  LCP: { good: 2500, poor: 4000 },
  FID: { good: 100, poor: 300 },
  CLS: { good: 0.1, poor: 0.25 },
  TTFB: { good: 800, poor: 1800 }
}

const getPerformanceRating = (metricName: string, value: number): 'good' | 'needs-improvement' | 'poor' => {
  const threshold = THRESHOLDS[metricName as keyof typeof THRESHOLDS]
  if (!threshold) return 'good'

  if (value <= threshold.good) return 'good'
  if (value <= threshold.poor) return 'needs-improvement'
  return 'poor'
}

export const PerformanceMonitor = () => {
  const { webVitals } = useAppStore()

  return (
    <div className="fixed bottom-4 right-4 bg-white border border-gray-200 rounded-lg p-3 shadow-lg text-xs font-mono z-50">
      <div className="text-xs font-semibold mb-2 text-gray-700">Web Vitals</div>
      <div className="space-y-1">
        {Object.entries(webVitals).map(([key, value]) => {
          const rating = getPerformanceRating(key.toUpperCase(), value as number)
          const color = rating === 'good' ? 'text-green-600' :
                      rating === 'needs-improvement' ? 'text-yellow-600' : 'text-red-600'

          return (
            <div key={key} className="flex justify-between gap-2">
              <span className="text-gray-600">{key.toUpperCase()}:</span>
              <span className={color}>
                {key === 'cls' ? (value as number).toFixed(3) : Math.round(value as number)}
                {key !== 'cls' && 'ms'}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}