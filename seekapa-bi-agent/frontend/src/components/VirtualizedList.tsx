import { useVirtualizer } from '@tanstack/react-virtual'
import { useRef, useMemo } from 'react'
import { motion } from 'framer-motion'

interface VirtualizedListProps<T> {
  items: T[]
  height: number
  itemHeight: number
  renderItem: (item: T, index: number) => React.ReactNode
  className?: string
  overscan?: number
}

const VirtualizedList = <T extends { id: string | number }>({
  items,
  height,
  itemHeight,
  renderItem,
  className = '',
  overscan = 5
}: VirtualizedListProps<T>) => {
  const parentRef = useRef<HTMLDivElement>(null)

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => itemHeight,
    overscan
  })

  const virtualItems = virtualizer.getVirtualItems()

  return (
    <div
      ref={parentRef}
      className={`overflow-auto ${className}`}
      style={{ height }}
    >
      <div
        style={{
          height: virtualizer.getTotalSize(),
          width: '100%',
          position: 'relative'
        }}
      >
        {virtualItems.map((virtualItem) => {
          const item = items[virtualItem.index]
          return (
            <motion.div
              key={virtualItem.key}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2 }}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: virtualItem.size,
                transform: `translateY(${virtualItem.start}px)`
              }}
            >
              {renderItem(item, virtualItem.index)}
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}

export default VirtualizedList

// Example usage component for data insights
export const DataInsightsList = ({ insights }: { insights: Array<{ id: string; title: string; description: string; severity: 'info' | 'warning' | 'critical' }> }) => {
  const renderInsightItem = (insight: typeof insights[0], _index: number) => (
    <motion.div
      whileHover={{ scale: 1.02 }}
      className="p-4 bg-white border border-gray-200 rounded-lg shadow-sm mx-2 mb-2"
    >
      <div className="flex items-start gap-3">
        <div className={`w-3 h-3 rounded-full mt-1 ${
          insight.severity === 'critical' ? 'bg-red-500' :
          insight.severity === 'warning' ? 'bg-yellow-500' : 'bg-blue-500'
        }`} />
        <div className="flex-1">
          <h3 className="font-medium text-gray-900">{insight.title}</h3>
          <p className="text-sm text-gray-600 mt-1">{insight.description}</p>
        </div>
      </div>
    </motion.div>
  )

  return (
    <VirtualizedList
      items={insights}
      height={400}
      itemHeight={120}
      renderItem={renderInsightItem}
      className="border border-gray-200 rounded-lg"
    />
  )
}

// High-performance table component for large datasets
export const VirtualizedTable = <T extends { id: string | number }>({
  data,
  columns,
  height = 400
}: {
  data: T[]
  columns: Array<{
    key: keyof T
    header: string
    width: number
    render?: (value: any, item: T) => React.ReactNode
  }>
  height?: number
}) => {
  const totalWidth = useMemo(() => columns.reduce((sum, col) => sum + col.width, 0), [columns])

  const renderRow = (item: T, _index: number) => (
    <div
      className="flex border-b border-gray-100 hover:bg-gray-50 transition-colors"
      style={{ width: totalWidth }}
    >
      {columns.map((column) => (
        <div
          key={String(column.key)}
          className="px-4 py-3 text-sm"
          style={{ width: column.width, minWidth: column.width }}
        >
          {column.render
            ? column.render(item[column.key], item)
            : String(item[column.key])
          }
        </div>
      ))}
    </div>
  )

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="bg-gray-50 border-b border-gray-200 sticky top-0 z-10">
        <div className="flex" style={{ width: totalWidth }}>
          {columns.map((column) => (
            <div
              key={String(column.key)}
              className="px-4 py-3 text-sm font-medium text-gray-700"
              style={{ width: column.width, minWidth: column.width }}
            >
              {column.header}
            </div>
          ))}
        </div>
      </div>

      {/* Virtual List */}
      <VirtualizedList
        items={data}
        height={height}
        itemHeight={48}
        renderItem={renderRow}
        className="overflow-x-auto"
      />
    </div>
  )
}