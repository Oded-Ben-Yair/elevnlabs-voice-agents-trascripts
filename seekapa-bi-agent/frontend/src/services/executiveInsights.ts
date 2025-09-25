import { useState, useEffect, useRef } from 'react'
// import { useAppStore } from '../store' // Reserved for future integration

export interface ExecutiveKPIs {
  revenue: number
  revenueChange: number
  customers: number
  customerChange: number
  marketShare: number
  marketShareChange: number
  conversionRate: number
  conversionChange: number
}

export interface ExecutiveInsight {
  id: string
  title: string
  description: string
  severity: 'info' | 'warning' | 'critical'
  category: 'revenue' | 'customers' | 'operations' | 'market'
  impact: 'high' | 'medium' | 'low'
  timestamp: string
  actions: string[]
  dataPoints: {
    current: number
    previous: number
    target?: number
  }
}

export interface ExecutiveMetrics {
  kpis: ExecutiveKPIs
  insights: ExecutiveInsight[]
  executiveSummary: string
  trendAnalysis: {
    revenue: 'positive' | 'negative' | 'neutral'
    growth: 'accelerating' | 'steady' | 'declining'
    risk: 'low' | 'medium' | 'high'
  }
}

// Simulated data - In production, this would come from your backend/Power BI API
const generateMockKPIs = (): ExecutiveKPIs => {
  const baseRevenue = 12500000
  const baseCustomers = 45000
  const baseMarketShare = 23.5
  const baseConversion = 3.2

  // Add some randomness for demo purposes
  const revenueVariation = (Math.random() - 0.5) * 0.3 // ±15%
  const customerVariation = (Math.random() - 0.5) * 0.2 // ±10%
  const marketShareVariation = (Math.random() - 0.5) * 0.1 // ±5%
  const conversionVariation = (Math.random() - 0.5) * 0.4 // ±20%

  return {
    revenue: Math.round(baseRevenue * (1 + revenueVariation)),
    revenueChange: Math.round(revenueVariation * 100 * 10) / 10, // One decimal place
    customers: Math.round(baseCustomers * (1 + customerVariation)),
    customerChange: Math.round(customerVariation * 100 * 10) / 10,
    marketShare: Math.round((baseMarketShare * (1 + marketShareVariation)) * 10) / 10,
    marketShareChange: Math.round(marketShareVariation * 100 * 10) / 10,
    conversionRate: Math.round((baseConversion * (1 + conversionVariation)) * 10) / 10,
    conversionChange: Math.round(conversionVariation * 100 * 10) / 10
  }
}

const generateMockInsights = (kpis: ExecutiveKPIs): ExecutiveInsight[] => {
  const insights: ExecutiveInsight[] = []

  // Revenue insights
  if (kpis.revenueChange > 10) {
    insights.push({
      id: 'rev-growth-high',
      title: 'Strong Revenue Growth',
      description: `Revenue has increased by ${kpis.revenueChange}% compared to last period, significantly outperforming targets.`,
      severity: 'info',
      category: 'revenue',
      impact: 'high',
      timestamp: new Date().toISOString(),
      actions: ['Analyze growth drivers', 'Scale successful initiatives', 'Optimize resource allocation'],
      dataPoints: {
        current: kpis.revenue,
        previous: Math.round(kpis.revenue / (1 + kpis.revenueChange / 100)),
        target: kpis.revenue * 0.95
      }
    })
  } else if (kpis.revenueChange < -5) {
    insights.push({
      id: 'rev-decline',
      title: 'Revenue Decline Detected',
      description: `Revenue has decreased by ${Math.abs(kpis.revenueChange)}% which requires immediate attention.`,
      severity: 'critical',
      category: 'revenue',
      impact: 'high',
      timestamp: new Date().toISOString(),
      actions: ['Identify root causes', 'Implement recovery plan', 'Review market conditions'],
      dataPoints: {
        current: kpis.revenue,
        previous: Math.round(kpis.revenue / (1 + kpis.revenueChange / 100))
      }
    })
  }

  // Customer insights
  if (kpis.customerChange > 8) {
    insights.push({
      id: 'cust-growth-strong',
      title: 'Exceptional Customer Acquisition',
      description: `Customer base grew by ${kpis.customerChange}%, indicating strong market traction.`,
      severity: 'info',
      category: 'customers',
      impact: 'high',
      timestamp: new Date().toISOString(),
      actions: ['Scale acquisition channels', 'Improve onboarding', 'Focus on retention'],
      dataPoints: {
        current: kpis.customers,
        previous: Math.round(kpis.customers / (1 + kpis.customerChange / 100))
      }
    })
  }

  // Market share insights
  if (kpis.marketShareChange < -2) {
    insights.push({
      id: 'market-share-loss',
      title: 'Market Share Erosion',
      description: `Market share declined by ${Math.abs(kpis.marketShareChange)}%, potentially due to increased competition.`,
      severity: 'warning',
      category: 'market',
      impact: 'medium',
      timestamp: new Date().toISOString(),
      actions: ['Competitive analysis', 'Product differentiation', 'Marketing strategy review'],
      dataPoints: {
        current: kpis.marketShare,
        previous: kpis.marketShare - kpis.marketShareChange
      }
    })
  }

  // Conversion insights
  if (kpis.conversionChange > 15) {
    insights.push({
      id: 'conversion-improvement',
      title: 'Conversion Rate Optimization Success',
      description: `Conversion rate improved by ${kpis.conversionChange}%, driving better ROI on marketing spend.`,
      severity: 'info',
      category: 'operations',
      impact: 'medium',
      timestamp: new Date().toISOString(),
      actions: ['Document best practices', 'Scale optimization efforts', 'A/B test further improvements'],
      dataPoints: {
        current: kpis.conversionRate,
        previous: kpis.conversionRate / (1 + kpis.conversionChange / 100)
      }
    })
  }

  return insights
}

const generateExecutiveSummary = (kpis: ExecutiveKPIs, insights: ExecutiveInsight[]): string => {
  const revenueStatus = kpis.revenueChange > 5 ? 'strong' : kpis.revenueChange < -2 ? 'concerning' : 'stable'
  const customerStatus = kpis.customerChange > 5 ? 'growing' : kpis.customerChange < -2 ? 'declining' : 'stable'
  const criticalIssues = insights.filter(i => i.severity === 'critical').length

  let summary = `Business performance this period shows ${revenueStatus} revenue trends with ${customerStatus} customer metrics. `

  if (kpis.revenueChange > 10) {
    summary += `Exceptional revenue growth of ${kpis.revenueChange}% demonstrates strong market position. `
  }

  if (criticalIssues > 0) {
    summary += `However, ${criticalIssues} critical issue${criticalIssues > 1 ? 's' : ''} require immediate executive attention. `
  }

  if (kpis.marketShareChange > 2) {
    summary += `Market share expansion of ${kpis.marketShareChange}% indicates competitive advantage. `
  }

  summary += `Key focus areas include customer acquisition, operational efficiency, and strategic market positioning.`

  return summary
}

// Custom hook for executive insights
export const useExecutiveInsights = () => {
  const [metrics, setMetrics] = useState<ExecutiveMetrics | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const refreshIntervalRef = useRef<number | null>(null)

  // const { insights: storeInsights } = useAppStore() // Reserved for future use

  const loadExecutiveData = async () => {
    try {
      setIsLoading(true)
      setError(null)

      // Simulate API call delay
      await new Promise(resolve => setTimeout(resolve, 800))

      const kpis = generateMockKPIs()
      const executiveInsights = generateMockInsights(kpis)
      const executiveSummary = generateExecutiveSummary(kpis, executiveInsights)

      const newMetrics: ExecutiveMetrics = {
        kpis,
        insights: executiveInsights,
        executiveSummary,
        trendAnalysis: {
          revenue: kpis.revenueChange > 5 ? 'positive' : kpis.revenueChange < -2 ? 'negative' : 'neutral',
          growth: kpis.customerChange > 8 ? 'accelerating' : kpis.customerChange < -2 ? 'declining' : 'steady',
          risk: executiveInsights.some(i => i.severity === 'critical') ? 'high' :
                 executiveInsights.some(i => i.severity === 'warning') ? 'medium' : 'low'
        }
      }

      setMetrics(newMetrics)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load executive data')
    } finally {
      setIsLoading(false)
    }
  }

  const refreshData = () => {
    loadExecutiveData()
  }

  useEffect(() => {
    // Initial load
    loadExecutiveData()

    // Set up auto-refresh every 5 minutes
    refreshIntervalRef.current = window.setInterval(loadExecutiveData, 5 * 60 * 1000)

    return () => {
      if (refreshIntervalRef.current) {
        window.clearInterval(refreshIntervalRef.current)
      }
    }
  }, [])

  return {
    kpis: metrics?.kpis || {
      revenue: 0,
      revenueChange: 0,
      customers: 0,
      customerChange: 0,
      marketShare: 0,
      marketShareChange: 0,
      conversionRate: 0,
      conversionChange: 0
    },
    insights: metrics?.insights || [],
    executiveSummary: metrics?.executiveSummary || 'Loading executive summary...',
    trendAnalysis: metrics?.trendAnalysis || {
      revenue: 'neutral' as const,
      growth: 'steady' as const,
      risk: 'low' as const
    },
    isLoading,
    error,
    refreshData
  }
}

// Utility functions for executive insights
export const formatCurrency = (amount: number): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(amount)
}

export const formatPercentage = (value: number): string => {
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

export const getInsightPriority = (insight: ExecutiveInsight): number => {
  const severityWeight = {
    critical: 100,
    warning: 50,
    info: 10
  }

  const impactWeight = {
    high: 30,
    medium: 20,
    low: 10
  }

  return severityWeight[insight.severity] + impactWeight[insight.impact]
}

export const categorizeInsights = (insights: ExecutiveInsight[]) => {
  return insights.reduce((acc, insight) => {
    if (!acc[insight.category]) {
      acc[insight.category] = []
    }
    acc[insight.category].push(insight)
    return acc
  }, {} as Record<string, ExecutiveInsight[]>)
}