import { motion } from 'framer-motion'
import { BarChart3, X } from 'lucide-react'
import { useAppStore } from '../store'
import { DataInsightsList } from './VirtualizedList'

const InsightsDashboard = () => {
  const { insights, showInsights, setShowInsights } = useAppStore()

  if (!showInsights) return null


  return (
    <motion.div
      initial={{ opacity: 0, x: 300 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 300 }}
      className="fixed right-0 top-0 h-full w-96 bg-white border-l border-gray-200 shadow-xl z-50"
    >
      <div className="flex items-center justify-between p-6 border-b border-gray-200">
        <div className="flex items-center gap-3">
          <BarChart3 className="w-6 h-6 text-blue-600" />
          <h2 className="text-lg font-semibold">Data Insights</h2>
        </div>
        <button
          onClick={() => setShowInsights(false)}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="p-6">
        {insights.length === 0 ? (
          <div className="text-center py-12">
            <BarChart3 className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-500">No insights available yet</p>
            <p className="text-sm text-gray-400 mt-1">
              Start chatting to generate insights
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-gray-700">
                Recent Insights ({insights.length})
              </h3>
            </div>

            <DataInsightsList insights={insights} />
          </div>
        )}
      </div>
    </motion.div>
  )
}

export default InsightsDashboard