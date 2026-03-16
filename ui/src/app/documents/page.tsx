'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { UploadZone } from '@/components/documents/UploadZone'
import { DocumentTable } from '@/components/documents/DocumentTable'
import { listDocuments } from '@/lib/api'
import type { Document } from '@/lib/types'

const POLL_INTERVAL_MS = 5000

function hasInProgressDocuments(docs: Document[]): boolean {
  return docs.some((d) => d.status === 'pending' || d.status === 'processing')
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [showUpload, setShowUpload] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchDocuments = useCallback(async () => {
    try {
      const data = await listDocuments(1, 50)
      setDocuments(data.items)
    } catch {
      // Error handled silently; user sees stale data
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    if (hasInProgressDocuments(documents)) {
      pollRef.current = setInterval(fetchDocuments, POLL_INTERVAL_MS)
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [documents, fetchDocuments])

  function handleUploaded() {
    setShowUpload(false)
    fetchDocuments()
  }

  return (
    <DashboardLayout>
      <div className="p-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Documents</h1>
            <p className="text-sm text-gray-500 mt-1">
              Manage your uploaded documents for RAG queries
            </p>
          </div>
          <button
            onClick={() => setShowUpload((v) => !v)}
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 transition-colors"
          >
            {showUpload ? 'Cancel' : '+ Upload'}
          </button>
        </div>

        {showUpload && (
          <div className="mb-6">
            <UploadZone onUploaded={handleUploaded} />
          </div>
        )}

        <DocumentTable
          documents={documents}
          loading={loading}
          onDeleted={fetchDocuments}
        />
      </div>
    </DashboardLayout>
  )
}
