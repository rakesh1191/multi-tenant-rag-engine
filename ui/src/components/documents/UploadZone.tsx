'use client'

import { useCallback, useRef, useState } from 'react'
import { Upload, File, X } from 'lucide-react'
import { Progress } from '@/components/ui/progress'
import { Button } from '@/components/ui/button'
import { uploadDocument } from '@/lib/api'
import { toast } from 'sonner'

interface UploadZoneProps {
  onUploaded: () => void
}

interface PendingFile {
  file: File
  progress: number
  status: 'pending' | 'uploading' | 'done' | 'error'
}

const ACCEPTED_TYPES = ['application/pdf', 'text/plain', 'text/markdown']
const ACCEPTED_EXTENSIONS = ['.pdf', '.txt', '.md']

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function UploadZone({ onUploaded }: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const addFiles = useCallback((files: FileList | File[]) => {
    const newFiles = Array.from(files).filter((f) =>
      ACCEPTED_TYPES.includes(f.type) ||
      ACCEPTED_EXTENSIONS.some((ext) => f.name.toLowerCase().endsWith(ext))
    )
    if (newFiles.length === 0) {
      toast.error('Only PDF, TXT, and MD files are accepted')
      return
    }
    setPendingFiles((prev) => [
      ...prev,
      ...newFiles.map((file) => ({ file, progress: 0, status: 'pending' as const })),
    ])
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      setIsDragging(false)
      addFiles(e.dataTransfer.files)
    },
    [addFiles]
  )

  const removeFile = (index: number) => {
    setPendingFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const handleUpload = async () => {
    const toUpload = pendingFiles.filter((pf) => pf.status === 'pending')
    if (toUpload.length === 0) return
    setIsUploading(true)
    for (let i = 0; i < pendingFiles.length; i++) {
      if (pendingFiles[i].status !== 'pending') continue
      setPendingFiles((prev) =>
        prev.map((pf, idx) => (idx === i ? { ...pf, status: 'uploading' } : pf))
      )
      try {
        await uploadDocument(pendingFiles[i].file, (pct) => {
          setPendingFiles((prev) =>
            prev.map((pf, idx) => (idx === i ? { ...pf, progress: pct } : pf))
          )
        })
        setPendingFiles((prev) =>
          prev.map((pf, idx) =>
            idx === i ? { ...pf, status: 'done', progress: 100 } : pf
          )
        )
        toast.success(`${pendingFiles[i].file.name} uploaded`)
      } catch {
        setPendingFiles((prev) =>
          prev.map((pf, idx) => (idx === i ? { ...pf, status: 'error' } : pf))
        )
        toast.error(`Failed to upload ${pendingFiles[i].file.name}`)
      }
    }
    setIsUploading(false)
    onUploaded()
    setTimeout(() => {
      setPendingFiles((prev) => prev.filter((pf) => pf.status !== 'done'))
    }, 1500)
  }

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`
          flex flex-col items-center justify-center rounded-xl border-2 border-dashed
          cursor-pointer transition-colors p-10 text-center
          ${isDragging ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-indigo-400 bg-white'}
        `}
      >
        <Upload className="h-10 w-10 text-gray-400 mb-3" />
        <p className="text-sm font-medium text-gray-700">
          Drag & drop files here, or click to browse
        </p>
        <p className="text-xs text-gray-500 mt-1">PDF, TXT, MD files accepted</p>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          multiple
          accept=".pdf,.txt,.md"
          onChange={(e) => e.target.files && addFiles(e.target.files)}
        />
      </div>

      {pendingFiles.length > 0 && (
        <div className="space-y-2">
          {pendingFiles.map((pf, i) => (
            <div key={i} className="flex items-center gap-3 rounded-lg border bg-white p-3">
              <File className="h-5 w-5 text-gray-400 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{pf.file.name}</p>
                <p className="text-xs text-gray-500">{formatBytes(pf.file.size)}</p>
                {pf.status === 'uploading' && (
                  <Progress value={pf.progress} className="h-1 mt-1" />
                )}
              </div>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                pf.status === 'done' ? 'bg-green-100 text-green-700' :
                pf.status === 'error' ? 'bg-red-100 text-red-700' :
                pf.status === 'uploading' ? 'bg-blue-100 text-blue-700' :
                'bg-gray-100 text-gray-600'
              }`}>
                {pf.status === 'done' ? 'Done' :
                 pf.status === 'error' ? 'Error' :
                 pf.status === 'uploading' ? `${pf.progress}%` : 'Ready'}
              </span>
              {pf.status === 'pending' && (
                <button onClick={(e) => { e.stopPropagation(); removeFile(i) }}>
                  <X className="h-4 w-4 text-gray-400 hover:text-gray-600" />
                </button>
              )}
            </div>
          ))}
          <div className="flex justify-end">
            <Button
              onClick={handleUpload}
              disabled={isUploading || pendingFiles.every((pf) => pf.status !== 'pending')}
            >
              {isUploading ? 'Uploading...' : `Upload ${pendingFiles.filter((pf) => pf.status === 'pending').length} file(s)`}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
