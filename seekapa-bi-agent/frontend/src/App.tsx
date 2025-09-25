import { useEffect, useState, Suspense } from 'react'
import { AnimatePresence } from 'framer-motion'
import { Sparkles, BarChart3, Settings, Menu, X } from 'lucide-react'
import { useAppStore } from './store'
import { initializeWebVitalsTracking } from './utils/webVitals'
import { PerformanceMonitor } from './components/PerformanceMonitor'
import { preloadComponents } from './components/LazyComponents'
import './App.css'

// Lazy-loaded components for code splitting
import { lazy } from 'react'
const ChatInterface = lazy(() => import('./components/ChatInterface'))
const InsightsDashboard = lazy(() => import('./components/InsightsDashboard'))
const DataVisualization = lazy(() => import('./components/DataVisualization'))
const SettingsPanel = lazy(() => import('./components/SettingsPanel'))

// Loading component
const LoadingSpinner = () => (
  <div className="flex items-center justify-center h-full">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
  </div>
)

// Navigation component
const Navigation = ({ currentRoute, onRouteChange }: { currentRoute: string; onRouteChange: (route: string) => void }) => {
  const { showInsights, setShowInsights } = useAppStore()
  const [showMobileMenu, setShowMobileMenu] = useState(false)

  const navItems = [
    { id: 'chat', icon: Sparkles, label: 'Chat' },
    { id: 'visualizations', icon: BarChart3, label: 'Data' },
    { id: 'settings', icon: Settings, label: 'Settings' }
  ]

  return (
    <div className="bg-white border-b border-gray-200 px-6 py-4 relative">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
            <Sparkles className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">Seekapa Copilot</h1>
            <p className="text-xs text-gray-500">Powered by Azure GPT-5 + Power BI</p>
          </div>
        </div>

        {/* Desktop Navigation */}
        <div className="hidden md:flex items-center gap-4">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => onRouteChange(item.id)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${
                currentRoute === item.id
                  ? 'bg-blue-100 text-blue-700'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <item.icon className="w-4 h-4" />
              <span className="text-sm font-medium">{item.label}</span>
            </button>
          ))}
          <button
            onClick={() => setShowInsights(!showInsights)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${
              showInsights
                ? 'bg-blue-100 text-blue-700'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            <span className="text-sm font-medium">Insights</span>
          </button>
        </div>

        {/* Mobile Menu Button */}
        <button
          onClick={() => setShowMobileMenu(!showMobileMenu)}
          className="md:hidden p-2 rounded-lg hover:bg-gray-100"
        >
          {showMobileMenu ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile Navigation */}
      <AnimatePresence>
        {showMobileMenu && (
          <div className="absolute top-full left-0 right-0 bg-white border-b border-gray-200 md:hidden z-40">
            <div className="px-6 py-4 space-y-2">
              {navItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => {
                    onRouteChange(item.id)
                    setShowMobileMenu(false)
                  }}
                  className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg transition-colors ${
                    currentRoute === item.id
                      ? 'bg-blue-100 text-blue-700'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  <item.icon className="w-4 h-4" />
                  <span className="text-sm font-medium">{item.label}</span>
                </button>
              ))}
              <button
                onClick={() => {
                  setShowInsights(!showInsights)
                  setShowMobileMenu(false)
                }}
                className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg transition-colors ${
                  showInsights
                    ? 'bg-blue-100 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                <BarChart3 className="w-4 h-4" />
                <span className="text-sm font-medium">Insights</span>
              </button>
            </div>
          </div>
        )}
      </AnimatePresence>
    </div>
  )
}

// Main App component
function App() {
  const [currentRoute, setCurrentRoute] = useState('chat')

  useEffect(() => {
    // Initialize Web Vitals tracking
    initializeWebVitalsTracking()

    // Preload components for better performance
    preloadComponents()
  }, [])

  const renderCurrentRoute = () => {
    switch (currentRoute) {
      case 'chat':
        return (
          <Suspense fallback={<LoadingSpinner />}>
            <ChatInterface />
          </Suspense>
        )
      case 'visualizations':
        return (
          <Suspense fallback={<LoadingSpinner />}>
            <DataVisualization />
          </Suspense>
        )
      case 'settings':
        return (
          <Suspense fallback={<LoadingSpinner />}>
            <SettingsPanel />
          </Suspense>
        )
      default:
        return (
          <Suspense fallback={<LoadingSpinner />}>
            <ChatInterface />
          </Suspense>
        )
    }
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <div className="flex-1 flex flex-col">
        <Navigation currentRoute={currentRoute} onRouteChange={setCurrentRoute} />
        <div className="flex-1 relative">
          {renderCurrentRoute()}

          {/* Insights Dashboard Overlay */}
          <AnimatePresence>
            <Suspense fallback={null}>
              <InsightsDashboard />
            </Suspense>
          </AnimatePresence>
        </div>
      </div>

      {/* Performance Monitor (only in development) */}
      {import.meta.env.DEV && <PerformanceMonitor />}
    </div>
  )
}

export default App
