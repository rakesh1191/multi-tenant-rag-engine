'use client'

import { useState } from 'react'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { ChatInput } from '@/components/chat/ChatInput'
import { SourceCard } from '@/components/chat/SourceCard'
import { queryStream } from '@/lib/api'
import type { SourceChunk } from '@/lib/types'
import { toast } from 'sonner'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputValue, setInputValue] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [sources, setSources] = useState<SourceChunk[]>([])

  async function handleSend() {
    const query = inputValue.trim()
    if (!query || isStreaming) return
    setInputValue('')
    setSources([])
    setMessages((prev) => [...prev, { role: 'user', content: query }])
    setMessages((prev) => [...prev, { role: 'assistant', content: '', isStreaming: true }])
    setIsStreaming(true)

    try {
      const resp = await queryStream(query)
      if (!resp.ok) {
        throw new Error(`Server error: ${resp.status}`)
      }
      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()
      let fullAnswer = ''
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6).trim()
          if (data === '[DONE]') break
          try {
            const parsed = JSON.parse(data) as {
              type: string
              data?: string
              sources?: SourceChunk[]
            }
            if (parsed.type === 'token' && parsed.data) {
              fullAnswer += parsed.data
              const snap = fullAnswer
              setMessages((prev) => {
                const next = [...prev]
                next[next.length - 1] = { role: 'assistant', content: snap, isStreaming: true }
                return next
              })
            } else if (parsed.type === 'sources' && parsed.sources) {
              setSources(parsed.sources)
            }
          } catch {
            // Plain text token fallback
            if (data !== '[DONE]') {
              fullAnswer += data
              const snap = fullAnswer
              setMessages((prev) => {
                const next = [...prev]
                next[next.length - 1] = { role: 'assistant', content: snap, isStreaming: true }
                return next
              })
            }
          }
        }
      }

      setMessages((prev) => {
        const next = [...prev]
        next[next.length - 1] = { role: 'assistant', content: fullAnswer, isStreaming: false }
        return next
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Query failed'
      toast.error(message)
      setMessages((prev) => prev.slice(0, -1))
    } finally {
      setIsStreaming(false)
    }
  }

  return (
    <DashboardLayout>
      <div className="flex h-full">
        {/* Chat panel */}
        <div className="flex flex-1 flex-col">
          <div className="border-b px-6 py-4">
            <h1 className="text-xl font-bold text-gray-900">Chat</h1>
            <p className="text-sm text-gray-500">Ask questions about your documents</p>
          </div>
          <ChatWindow messages={messages} />
          <div className="border-t p-4">
            <ChatInput
              value={inputValue}
              onChange={setInputValue}
              onSend={handleSend}
              disabled={isStreaming}
            />
          </div>
        </div>

        {/* Sources panel */}
        <div className="w-80 border-l bg-gray-50 flex flex-col">
          <div className="border-b px-4 py-4">
            <h2 className="text-sm font-semibold text-gray-700">Sources</h2>
            <p className="text-xs text-gray-400 mt-0.5">Retrieved document chunks</p>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {sources.length === 0 ? (
              <p className="text-xs text-gray-400 text-center mt-8">
                Sources will appear here after your query
              </p>
            ) : (
              sources.map((source, i) => (
                <SourceCard key={`${source.document_id}-${source.chunk_index}`} source={source} index={i} />
              ))
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  )
}
