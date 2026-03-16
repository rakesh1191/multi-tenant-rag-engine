'use client'

import { useCallback, useEffect, useState } from 'react'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { getHistory } from '@/lib/api'
import type { QueryHistoryItem } from '@/lib/types'

const PAGE_SIZES = [10, 20, 50]

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function HistoryPage() {
  const [items, setItems] = useState<QueryHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [selected, setSelected] = useState<QueryHistoryItem | null>(null)

  const fetchHistory = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getHistory(page, pageSize)
      setItems(data.items)
      setTotal(data.total)
      setTotalPages(Math.max(1, Math.ceil(data.total / pageSize)))
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [page, pageSize])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  function handlePageSizeChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setPageSize(Number(e.target.value))
    setPage(1)
  }

  return (
    <DashboardLayout>
      <div className="p-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Query History</h1>
            <p className="text-sm text-gray-500 mt-1">
              {total} total queries
            </p>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-600">Rows per page:</label>
            <select
              value={pageSize}
              onChange={handlePageSizeChange}
              className="rounded-md border bg-white px-2 py-1.5 text-sm"
            >
              {PAGE_SIZES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-xl border bg-white py-16 text-center text-gray-500">
            <p className="text-sm">No queries yet. Try asking a question in the Chat page.</p>
          </div>
        ) : (
          <div className="rounded-xl border bg-white overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-gray-50">
                  <TableHead className="w-1/3">Query</TableHead>
                  <TableHead className="w-1/3">Answer</TableHead>
                  <TableHead>Latency</TableHead>
                  <TableHead>Cache</TableHead>
                  <TableHead>Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow
                    key={item.id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => setSelected(item)}
                  >
                    <TableCell className="max-w-xs">
                      <p className="text-sm text-gray-800 truncate">{item.query_text}</p>
                    </TableCell>
                    <TableCell className="max-w-xs">
                      <p className="text-sm text-gray-500 truncate">
                        {item.response_text
                          ? item.response_text.length > 100
                            ? item.response_text.slice(0, 100) + '…'
                            : item.response_text
                          : '—'}
                      </p>
                    </TableCell>
                    <TableCell className="text-sm text-gray-500">{item.latency_ms ?? '—'}ms</TableCell>
                    <TableCell>
                      {item.cache_hit ? (
                        <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                          Hit
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                          Miss
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-gray-500">{formatDate(item.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-gray-500">
              Page {page} of {totalPages}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="rounded-md border px-3 py-1.5 text-sm disabled:opacity-50 hover:bg-gray-50"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="rounded-md border px-3 py-1.5 text-sm disabled:opacity-50 hover:bg-gray-50"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Row detail dialog */}
      <Dialog open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Query Detail</DialogTitle>
          </DialogHeader>
          {selected && (
            <div className="space-y-4">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Query</p>
                <p className="text-sm text-gray-800 bg-gray-50 rounded-lg p-3 whitespace-pre-wrap">{selected.query_text}</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Answer</p>
                <p className="text-sm text-gray-800 bg-gray-50 rounded-lg p-3 whitespace-pre-wrap">{selected.response_text ?? '—'}</p>
              </div>
              <div className="flex gap-6 text-sm text-gray-500">
                <span>Latency: <strong>{selected.latency_ms ?? '—'}ms</strong></span>
                <span>Cache: <strong>{selected.cache_hit ? 'Hit' : 'Miss'}</strong></span>
                <span>Date: <strong>{formatDate(selected.created_at)}</strong></span>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  )
}
