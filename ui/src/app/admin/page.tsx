'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { StatsCards } from '@/components/admin/StatsCards'
import { getStats } from '@/lib/api'
import { getTokenPayload } from '@/lib/auth'
import type { AdminStats } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function AdminPage() {
  const router = useRouter()
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [loading, setLoading] = useState(true)
  const payload = getTokenPayload()

  useEffect(() => {
    if (payload?.role !== 'admin') {
      router.replace('/documents')
      return
    }
    getStats()
      .then(setStats)
      .catch(() => {/* silent */})
      .finally(() => setLoading(false))
  }, [router, payload?.role])

  if (payload?.role !== 'admin') return null

  return (
    <DashboardLayout>
      <div className="p-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Admin Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">Platform-wide metrics and management</p>
        </div>

        <StatsCards stats={stats} loading={loading} />

        <div className="mt-8">
          <Card className="max-w-md">
            <CardHeader>
              <CardTitle className="text-base">Current Session</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">User ID</span>
                <span className="font-mono text-gray-800 text-xs truncate max-w-[200px]">{payload.sub}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Tenant ID</span>
                <span className="font-mono text-gray-800 text-xs truncate max-w-[200px]">{payload.tenant_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Role</span>
                <span className="font-medium capitalize text-indigo-600">{payload.role}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Token expires</span>
                <span className="text-gray-800">{new Date(payload.exp * 1000).toLocaleTimeString()}</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </DashboardLayout>
  )
}
