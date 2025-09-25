import { lazy, Suspense } from 'react'
import { Loader2 } from 'lucide-react'

// Loading component with smooth animation
const LoadingSpinner = () => (
  <div className="flex items-center justify-center p-8">
    <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
    <span className="ml-2 text-gray-600">Loading...</span>
  </div>
)

// Lazy load components for better performance
export const ChatInterface = lazy(() => import('./ChatInterface'))
export const InsightsDashboard = lazy(() => import('./InsightsDashboard'))
export const DataVisualization = lazy(() => import('./DataVisualization'))
export const SettingsPanel = lazy(() => import('./SettingsPanel'))
export const VirtualizedList = lazy(() => import('./VirtualizedList'))

// Higher-order component for lazy loading with suspense
export const withLazyLoading = <P extends object>(Component: React.ComponentType<P>) => {
  return (props: P) => (
    <Suspense fallback={<LoadingSpinner />}>
      <Component {...props} />
    </Suspense>
  )
}

// Pre-load components for better UX
export const preloadComponents = () => {
  // Preload commonly used components after initial render
  setTimeout(() => {
    import('./InsightsDashboard')
    import('./DataVisualization')
  }, 2000)
}