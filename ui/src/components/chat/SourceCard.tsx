'use client'

import { FileText } from 'lucide-react'
import type { SourceChunk } from '@/lib/types'

interface SourceCardProps {
  source: SourceChunk
  index: number
}

export function SourceCard({ source, index }: SourceCardProps) {
  const similarityPct = Math.round(source.similarity * 100)

  return (
    <div className="rounded-lg border bg-white p-3 flex items-center gap-3">
      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700 flex-shrink-0">
        {index + 1}
      </div>
      <FileText className="h-4 w-4 text-gray-400 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-800 truncate">{source.filename}</p>
        <p className="text-xs text-gray-500">Chunk #{source.chunk_index}</p>
      </div>
      <span className={`text-xs font-medium px-2 py-0.5 rounded-full flex-shrink-0 ${
        similarityPct >= 80 ? 'bg-green-100 text-green-700' :
        similarityPct >= 60 ? 'bg-yellow-100 text-yellow-700' :
        'bg-gray-100 text-gray-600'
      }`}>
        {similarityPct}%
      </span>
    </div>
  )
}
