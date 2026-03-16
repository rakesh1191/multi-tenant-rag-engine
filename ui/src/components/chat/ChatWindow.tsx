'use client'

import { useEffect, useRef } from 'react'
import { Bot, User } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkBreaks from 'remark-breaks'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
}

interface ChatWindowProps {
  messages: ChatMessage[]
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-1">
      <span className="h-2 w-2 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.3s]" />
      <span className="h-2 w-2 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.15s]" />
      <span className="h-2 w-2 rounded-full bg-gray-400 animate-bounce" />
    </div>
  )
}

export function ChatWindow({ messages }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center text-center text-gray-400 p-8">
        <Bot className="h-12 w-12 mb-4 text-gray-300" />
        <p className="text-sm font-medium">Upload documents first, then ask questions about them</p>
        <p className="text-xs mt-1">Your conversation will appear here</p>
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-6">
      {messages.map((msg, i) => (
        <div
          key={i}
          className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
        >
          <div className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full ${
            msg.role === 'user' ? 'bg-indigo-600' : 'bg-gray-200'
          }`}>
            {msg.role === 'user'
              ? <User className="h-4 w-4 text-white" />
              : <Bot className="h-4 w-4 text-gray-600" />
            }
          </div>
          <div
            className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
              msg.role === 'user'
                ? 'bg-indigo-600 text-white rounded-tr-sm'
                : 'bg-gray-100 text-gray-800 rounded-tl-sm'
            }`}
          >
            {msg.isStreaming && msg.content === '' ? (
              <TypingIndicator />
            ) : msg.role === 'assistant' ? (
              <div className="prose prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-li:my-0 prose-pre:bg-gray-800 prose-pre:text-gray-100 prose-code:text-indigo-700 prose-code:bg-indigo-50 prose-code:px-1 prose-code:rounded">
                <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>{msg.content}</ReactMarkdown>
              </div>
            ) : (
              <p className="whitespace-pre-wrap">{msg.content}</p>
            )}
            {msg.isStreaming && msg.content !== '' && (
              <span className="inline-block h-4 w-0.5 bg-gray-500 animate-pulse ml-0.5 align-middle" />
            )}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
