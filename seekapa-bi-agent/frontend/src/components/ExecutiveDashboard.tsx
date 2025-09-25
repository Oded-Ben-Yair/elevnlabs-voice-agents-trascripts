import { motion } from 'framer-motion'
import {
  TrendingUp, Users, DollarSign,
  BarChart3, Activity, Clock, Target, ArrowUpRight,
  ArrowDownRight, ChevronRight, Briefcase, Globe
} from 'lucide-react'
import { useAppStore } from '../store'
import { useExecutiveInsights } from '../services/executiveInsights'
import { memo, useMemo } from 'react'

// KPI Card Component
const KPICard = memo(({
  title,
  value,
  change,
  trend,
  icon: Icon,
  color = 'blue',
  onClick
}: {
  title: string
  value: string | number
  change: number
  trend: 'up' | 'down'
  icon: any
  color?: 'blue' | 'green' | 'red' | 'purple' | 'orange'
  onClick?: () => void
}) => {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-600 border-blue-200',
    green: 'bg-green-50 text-green-600 border-green-200',
    red: 'bg-red-50 text-red-600 border-red-200',
    purple: 'bg-purple-50 text-purple-600 border-purple-200',
    orange: 'bg-orange-50 text-orange-600 border-orange-200'
  }

  const trendColor = trend === 'up' ? 'text-green-600' : 'text-red-600'
  const TrendIcon = trend === 'up' ? ArrowUpRight : ArrowDownRight

  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      className={`bg-white rounded-xl border-2 p-6 cursor-pointer transition-all hover:shadow-lg ${
        onClick ? 'hover:border-blue-300' : ''
      }`}
      onClick={onClick}
    >
      <div className="flex items-start justify-between mb-4">
        <div className={`p-3 rounded-lg ${colorClasses[color]}`}>
          <Icon className="w-6 h-6" />
        </div>
        <div className={`flex items-center gap-1 ${trendColor}`}>
          <TrendIcon className="w-4 h-4" />
          <span className="text-sm font-medium">{Math.abs(change)}%</span>
        </div>
      </div>

      <div className="space-y-1">
        <h3 className="text-2xl font-bold text-gray-900">{value}</h3>
        <p className="text-sm text-gray-600">{title}</p>
      </div>

      {onClick && (
        <div className="flex items-center text-blue-600 text-sm font-medium mt-3">
          <span>View Details</span>
          <ChevronRight className="w-4 h-4 ml-1" />
        </div>
      )}
    </motion.div>
  )
})

// Executive Summary Card
const ExecutiveSummary = memo(({ summary }: { summary: string }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    className="bg-gradient-to-r from-blue-600 to-purple-600 rounded-xl p-6 text-white"
  >
    <div className="flex items-center gap-3 mb-4">
      <Briefcase className="w-6 h-6" />
      <h2 className="text-lg font-semibold">Executive Summary</h2>
    </div>
    <p className="text-blue-100 leading-relaxed">{summary}</p>
    <div className="flex items-center justify-between mt-4 pt-4 border-t border-blue-400">
      <span className="text-sm text-blue-200">Last updated: {new Date().toLocaleString()}</span>
      <button className="text-sm font-medium bg-white/20 px-3 py-1 rounded-lg hover:bg-white/30 transition-colors">
        Refresh
      </button>
    </div>
  </motion.div>
))

// Quick Action Button
const QuickActionButton = memo(({
  icon: Icon,
  label,
  onClick
}: {
  icon: any
  label: string
  onClick: () => void
}) => (
  <motion.button
    whileHover={{ scale: 1.05 }}
    whileTap={{ scale: 0.95 }}
    onClick={onClick}
    className="flex flex-col items-center gap-2 p-4 bg-white border border-gray-200 rounded-xl hover:border-blue-300 hover:shadow-md transition-all"
  >
    <Icon className="w-6 h-6 text-gray-600" />
    <span className="text-sm font-medium text-gray-700">{label}</span>
  </motion.button>
))

// Power BI Embed Component (Simplified for demo)
const PowerBIEmbed = memo(() => (
  <div className="bg-white rounded-xl border border-gray-200 p-4">
    <div className="flex items-center justify-between mb-4">
      <h3 className="text-lg font-semibold text-gray-900">Key Reports</h3>
      <button className="text-blue-600 text-sm font-medium hover:text-blue-800">
        View All Reports
      </button>
    </div>

    {/* Placeholder for Power BI embed */}
    <div className="bg-gray-50 rounded-lg h-64 flex items-center justify-center border-2 border-dashed border-gray-300">
      <div className="text-center">
        <BarChart3 className="w-12 h-12 text-gray-400 mx-auto mb-2" />
        <p className="text-gray-600 font-medium">Power BI Report</p>
        <p className="text-sm text-gray-500">Click to load interactive dashboard</p>
      </div>
    </div>
  </div>
))

// Main Executive Dashboard
const ExecutiveDashboard = () => {
  const { sendMessage } = useAppStore()
  const { insights, kpis, executiveSummary, isLoading } = useExecutiveInsights()

  // Memoized KPI data to prevent unnecessary re-renders
  const kpiData = useMemo(() => [
    {
      title: 'Revenue (YTD)',
      value: kpis.revenue.toLocaleString('en-US', { style: 'currency', currency: 'USD' }),
      change: kpis.revenueChange,
      trend: kpis.revenueChange >= 0 ? 'up' as const : 'down' as const,
      icon: DollarSign,
      color: 'green' as const,
      onClick: () => sendMessage('Show me detailed revenue analysis')
    },
    {
      title: 'Active Customers',
      value: kpis.customers.toLocaleString(),
      change: kpis.customerChange,
      trend: kpis.customerChange >= 0 ? 'up' as const : 'down' as const,
      icon: Users,
      color: 'blue' as const,
      onClick: () => sendMessage('Analyze customer growth trends')
    },
    {
      title: 'Market Share',
      value: `${kpis.marketShare}%`,
      change: kpis.marketShareChange,
      trend: kpis.marketShareChange >= 0 ? 'up' as const : 'down' as const,
      icon: Globe,
      color: 'purple' as const,
      onClick: () => sendMessage('Show market share analysis')
    },
    {
      title: 'Conversion Rate',
      value: `${kpis.conversionRate}%`,
      change: kpis.conversionChange,
      trend: kpis.conversionChange >= 0 ? 'up' as const : 'down' as const,
      icon: Target,
      color: 'orange' as const,
      onClick: () => sendMessage('Analyze conversion optimization opportunities')
    }
  ], [kpis, sendMessage])

  const quickActions = [
    { icon: BarChart3, label: 'View Reports', onClick: () => sendMessage('Show me all available reports') },
    { icon: TrendingUp, label: 'Growth Analysis', onClick: () => sendMessage('Analyze growth opportunities') },
    { icon: Users, label: 'Customer Insights', onClick: () => sendMessage('What are the key customer insights?') },
    { icon: Activity, label: 'Performance', onClick: () => sendMessage('Show performance metrics dashboard') }
  ]

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex items-center gap-3">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <span className="text-gray-600">Loading executive dashboard...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto bg-gray-50">
      <div className="max-w-7xl mx-auto p-6">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Executive Dashboard</h1>
              <p className="text-gray-600 mt-1">
                Real-time business intelligence and key performance indicators
              </p>
            </div>
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <Clock className="w-4 h-4" />
              <span>Last updated: {new Date().toLocaleTimeString()}</span>
            </div>
          </div>
        </motion.div>

        {/* Executive Summary */}
        <div className="mb-8">
          <ExecutiveSummary summary={executiveSummary} />
        </div>

        {/* KPI Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {kpiData.map((kpi, index) => (
            <motion.div
              key={kpi.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
            >
              <KPICard {...kpi} />
            </motion.div>
          ))}
        </div>

        {/* Quick Actions */}
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {quickActions.map((action, index) => (
              <motion.div
                key={action.label}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.4 + index * 0.05 }}
              >
                <QuickActionButton {...action} />
              </motion.div>
            ))}
          </div>
        </div>

        {/* Power BI Reports */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
          className="mb-8"
        >
          <PowerBIEmbed />
        </motion.div>

        {/* Key Insights */}
        {insights.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.7 }}
          >
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Key Insights</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {insights.slice(0, 4).map((insight) => (
                <div
                  key={insight.id}
                  className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow"
                >
                  <h3 className="font-medium text-gray-900 mb-2">{insight.title}</h3>
                  <p className="text-sm text-gray-600 mb-3">{insight.description}</p>
                  <div className="flex items-center justify-between">
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                      insight.severity === 'critical' ? 'bg-red-100 text-red-700' :
                      insight.severity === 'warning' ? 'bg-yellow-100 text-yellow-700' :
                      'bg-blue-100 text-blue-700'
                    }`}>
                      {insight.severity}
                    </span>
                    <button className="text-blue-600 text-sm font-medium hover:text-blue-800">
                      View Details
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  )
}

export default ExecutiveDashboard