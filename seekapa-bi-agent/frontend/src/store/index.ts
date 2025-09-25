import { create } from 'zustand'
import { subscribeWithSelector } from 'zustand/middleware'

interface Message {
  id: string
  type: 'user' | 'assistant'
  content: string
  timestamp: Date
  suggestions?: string[]
  context?: any
}

interface Insight {
  id: string
  title: string
  description: string
  severity: 'info' | 'warning' | 'critical'
  actions: string[]
  timestamp: string
}

interface AppState {
  // Chat state
  messages: Message[]
  input: string
  isTyping: boolean
  wsConnection: WebSocket | null

  // UI state
  insights: Insight[]
  showInsights: boolean

  // Performance tracking
  webVitals: {
    fcp?: number
    lcp?: number
    fid?: number
    cls?: number
    ttfb?: number
  }

  // Actions
  setMessages: (messages: Message[] | ((prev: Message[]) => Message[])) => void
  addMessage: (message: Message) => void
  setInput: (input: string) => void
  setIsTyping: (isTyping: boolean) => void
  setWsConnection: (ws: WebSocket | null) => void
  setInsights: (insights: Insight[]) => void
  setShowInsights: (show: boolean) => void
  setWebVitals: (vitals: Partial<AppState['webVitals']>) => void

  // WebSocket actions
  connectWebSocket: () => void
  disconnectWebSocket: () => void
  sendMessage: (message: string) => void
}

// WebSocket reconnection logic with exponential backoff
let reconnectAttempts = 0
const maxReconnectAttempts = 5
const baseDelay = 1000

const createWebSocketConnection = (store: any): WebSocket => {
  const ws = new WebSocket('ws://localhost:8000/ws/chat')

  ws.onopen = () => {
    console.log('Connected to Copilot')
    reconnectAttempts = 0
    store.getState().setWsConnection(ws)
  }

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.type === 'response') {
      store.getState().addMessage({
        id: Date.now().toString(),
        type: 'assistant',
        content: data.message,
        timestamp: new Date(),
        suggestions: data.suggestions,
        context: data.context
      })
      store.getState().setIsTyping(false)
    }
  }

  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
  }

  ws.onclose = () => {
    store.getState().setWsConnection(null)

    // Attempt reconnection with exponential backoff
    if (reconnectAttempts < maxReconnectAttempts) {
      const delay = Math.min(baseDelay * Math.pow(2, reconnectAttempts), 30000)
      console.log(`Attempting to reconnect in ${delay}ms... (attempt ${reconnectAttempts + 1}/${maxReconnectAttempts})`)

      setTimeout(() => {
        reconnectAttempts++
        store.getState().connectWebSocket()
      }, delay)
    } else {
      console.error('Max reconnection attempts reached')
    }
  }

  return ws
}

export const useAppStore = create<AppState>()(
  subscribeWithSelector((set, get) => ({
    // Initial state
    messages: [{
      id: '1',
      type: 'assistant',
      content: "Hello! I'm your Seekapa Copilot. I can help you analyze your Power BI data, uncover insights, and make data-driven decisions. What would you like to explore today?",
      timestamp: new Date(),
      suggestions: ["Show me today's sales performance", "What are the top trending products?", "Analyze customer behavior patterns"]
    }],
    input: '',
    isTyping: false,
    wsConnection: null,
    insights: [],
    showInsights: false,
    webVitals: {},

    // Actions
    setMessages: (messages) => set(state => ({
      messages: typeof messages === 'function' ? messages(state.messages) : messages
    })),

    addMessage: (message) => set(state => ({
      messages: [...state.messages, message]
    })),

    setInput: (input) => set({ input }),
    setIsTyping: (isTyping) => set({ isTyping }),
    setWsConnection: (wsConnection) => set({ wsConnection }),
    setInsights: (insights) => set({ insights }),
    setShowInsights: (showInsights) => set({ showInsights }),
    setWebVitals: (vitals) => set(state => ({
      webVitals: { ...state.webVitals, ...vitals }
    })),

    // WebSocket actions
    connectWebSocket: () => {
      const currentWs = get().wsConnection
      if (currentWs?.readyState === WebSocket.OPEN) {
        return
      }

      createWebSocketConnection({ getState: get })
    },

    disconnectWebSocket: () => {
      const ws = get().wsConnection
      if (ws) {
        ws.close()
        set({ wsConnection: null })
      }
    },

    sendMessage: (messageContent) => {
      const { wsConnection, addMessage, setInput, setIsTyping } = get()

      if (!messageContent.trim() || !wsConnection) return

      addMessage({
        id: Date.now().toString(),
        type: 'user',
        content: messageContent,
        timestamp: new Date()
      })

      setInput('')
      setIsTyping(true)
      wsConnection.send(JSON.stringify({ message: messageContent }))
    }
  }))
)

// Auto-connect WebSocket when store is created
useAppStore.getState().connectWebSocket()