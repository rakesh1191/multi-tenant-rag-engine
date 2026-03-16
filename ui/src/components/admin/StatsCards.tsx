'use client'

import { Users, FileText, MessageSquare, Building2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type { AdminStats } from '@/lib/types'

interface StatsCardsProps {
  stats: AdminStats | null
  loading: boolean
}

interface StatCard {
  title: string
  key: keyof AdminStats
  icon: React.ComponentType<{ className?: string }>
  color: string
}

const CARDS: StatCard[] = [
  { title: 'Users', key: 'user_count', icon: Users, color: 'text-blue-600' },
  { title: 'Documents', key: 'document_count', icon: FileText, color: 'text-green-600' },
  { title: 'Chunks', key: 'chunk_count', icon: Building2, color: 'text-purple-600' },
  { title: 'Queries', key: 'query_count', icon: MessageSquare, color: 'text-orange-600' },
]

export function StatsCards({ stats, loading }: StatsCardsProps) {
  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
      {CARDS.map((card) => {
        const Icon = card.icon
        return (
          <Card key={card.key} className="border shadow-sm">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">{card.title}</CardTitle>
              <Icon className={`h-5 w-5 ${card.color}`} />
            </CardHeader>
            <CardContent>
              {loading ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                <p className="text-3xl font-bold text-gray-900">
                  {stats ? stats[card.key].toLocaleString() : '—'}
                </p>
              )}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
