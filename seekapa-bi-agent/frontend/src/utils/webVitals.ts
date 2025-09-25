import { onCLS, onFCP, onFID, onLCP, onTTFB } from 'web-vitals'
import type { Metric } from 'web-vitals'
import { useAppStore } from '../store'

// Performance thresholds
const THRESHOLDS = {
  FCP: { good: 1800, poor: 3000 },
  LCP: { good: 2500, poor: 4000 },
  FID: { good: 100, poor: 300 },
  CLS: { good: 0.1, poor: 0.25 },
  TTFB: { good: 800, poor: 1800 }
}

export const getPerformanceRating = (metricName: string, value: number): 'good' | 'needs-improvement' | 'poor' => {
  const threshold = THRESHOLDS[metricName as keyof typeof THRESHOLDS]
  if (!threshold) return 'good'

  if (value <= threshold.good) return 'good'
  if (value <= threshold.poor) return 'needs-improvement'
  return 'poor'
}

export const initializeWebVitalsTracking = () => {
  const updateVitals = (metric: Metric) => {
    const { setWebVitals } = useAppStore.getState()

    setWebVitals({
      [metric.name.toLowerCase()]: metric.value
    })

    // Log performance metrics for monitoring
    console.log(`${metric.name}:`, {
      value: metric.value,
      rating: getPerformanceRating(metric.name, metric.value),
      delta: metric.delta,
      id: metric.id
    })

    // Send to analytics service (replace with your actual analytics)
    if (typeof window !== 'undefined' && (window as any).gtag) {
      (window as any).gtag('event', metric.name, {
        event_category: 'Web Vitals',
        event_label: metric.id,
        value: Math.round(metric.name === 'CLS' ? metric.value * 1000 : metric.value),
        custom_map: {
          metric_rating: getPerformanceRating(metric.name, metric.value)
        }
      })
    }
  }

  // Initialize all Web Vitals metrics
  onCLS(updateVitals)
  onFCP(updateVitals)
  onFID(updateVitals)
  onLCP(updateVitals)
  onTTFB(updateVitals)
}


// Custom hook for performance monitoring
export const usePerformanceTracking = () => {
  const { webVitals } = useAppStore()

  const trackCustomTiming = (name: string, startTime: number) => {
    const endTime = performance.now()
    const duration = endTime - startTime

    console.log(`Custom timing - ${name}:`, duration)

    // Send to analytics
    if (typeof window !== 'undefined' && (window as any).gtag) {
      (window as any).gtag('event', 'timing_complete', {
        name,
        value: Math.round(duration),
        event_category: 'Performance'
      })
    }

    return duration
  }

  const markTimeToInteractive = () => {
    const navigationEntry = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming
    const tti = navigationEntry.loadEventEnd - navigationEntry.fetchStart

    console.log('Time to Interactive:', tti)

    if (typeof window !== 'undefined' && (window as any).gtag) {
      (window as any).gtag('event', 'page_timing', {
        event_category: 'Performance',
        event_label: 'TTI',
        value: Math.round(tti)
      })
    }

    return tti
  }

  return {
    webVitals,
    trackCustomTiming,
    markTimeToInteractive
  }
}