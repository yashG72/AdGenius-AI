"use client"

import { FileTextIcon, RefreshCwIcon, Trash2Icon, UploadCloudIcon } from "lucide-react"
import { useRef, useState } from "react"
import { toast } from "sonner"

import { ConfirmDialog } from "@/components/app/confirm-dialog"
import { EmptyState } from "@/components/app/empty-state"
import { StatusBadge } from "@/components/app/status-badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { errorMessage } from "@/lib/api/errors"
import type { DocumentType } from "@/lib/api/types"
import { formatBytes, formatRelative, titleCase } from "@/lib/format"
import { useDocumentMutations, useDocuments } from "@/lib/queries/documents"
import { cn } from "@/lib/utils"

const DOCUMENT_TYPES: DocumentType[] = [
  "brand_guidelines",
  "product_catalogue",
  "product_specification",
  "previous_campaign",
  "marketing_strategy",
  "customer_persona",
  "competitor_analysis",
  "brand_tone",
  "other",
]
const ACCEPT = ".pdf,.docx,.txt,.csv"
const MAX_MB = 25

export function DocumentsPanel({ brandId, canDelete }: { brandId: string; canDelete: boolean }) {
  const { data, isPending, error } = useDocuments(brandId)
  const { upload, reindex, remove } = useDocumentMutations(brandId)
  const [documentType, setDocumentType] = useState<DocumentType>("brand_guidelines")
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function uploadFiles(files: FileList | null) {
    for (const file of Array.from(files ?? [])) {
      if (file.size > MAX_MB * 1024 * 1024) {
        toast.error(`${file.name} is larger than ${MAX_MB} MB`)
        continue
      }
      try {
        await upload.mutateAsync({ file, documentType })
        toast.success(`${file.name} uploaded — indexing in the background`)
      } catch (e) {
        toast.error(`${file.name}: ${errorMessage(e)}`)
      }
    }
    if (inputRef.current) inputRef.current.value = ""
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Upload documents</CardTitle>
          <CardDescription>
            Brand guidelines, product sheets, personas, past campaigns… PDF, DOCX, TXT or CSV up to {MAX_MB} MB.
            The Brand Research agent answers only from what you upload here.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Label htmlFor="doc-type" className="text-sm text-muted-foreground">
              Document type
            </Label>
            <Select value={documentType} onValueChange={(v) => setDocumentType(v as DocumentType)}>
              <SelectTrigger id="doc-type" className="w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DOCUMENT_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {titleCase(t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              void uploadFiles(e.dataTransfer.files)
            }}
            className={cn(
              "flex w-full flex-col items-center gap-2 rounded-xl border border-dashed px-6 py-10 text-center transition-colors",
              dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/40 hover:bg-accent/40",
            )}
          >
            <UploadCloudIcon className="size-6 text-muted-foreground" aria-hidden />
            <span className="text-sm">
              {upload.isPending ? "Uploading…" : "Drop files here or click to browse"}
            </span>
          </button>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            multiple
            hidden
            onChange={(e) => void uploadFiles(e.target.files)}
          />
        </CardContent>
      </Card>

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(error)}</AlertDescription>
        </Alert>
      ) : isPending ? (
        <Skeleton className="h-40 rounded-xl" />
      ) : data.items.length === 0 ? (
        <EmptyState
          icon={FileTextIcon}
          title="No documents yet"
          description="Upload the brand's guidelines first — they make the biggest difference to campaign quality."
        />
      ) : (
        <Card className="py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Document</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Chunks</TableHead>
                <TableHead className="text-right">Size</TableHead>
                <TableHead>Uploaded</TableHead>
                <TableHead className="pr-4 text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((doc) => (
                <TableRow key={doc.id}>
                  <TableCell className="max-w-72 pl-4">
                    <p className="truncate font-medium">{doc.original_filename}</p>
                    <p className="text-xs text-muted-foreground">
                      {titleCase(doc.document_type)}
                      {doc.page_count ? ` · ${doc.page_count} pages` : ""}
                    </p>
                    {doc.status === "failed" && doc.error_message && (
                      <p className="mt-1 text-xs text-red-300">{doc.error_message}</p>
                    )}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={doc.status} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{doc.chunk_count ?? "—"}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatBytes(doc.size_bytes)}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{formatRelative(doc.created_at)}</TableCell>
                  <TableCell className="pr-4 text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Re-index"
                        aria-label={`Re-index ${doc.original_filename}`}
                        disabled={doc.status === "processing" || reindex.isPending}
                        onClick={() =>
                          reindex.mutate(doc.id, {
                            onSuccess: () => toast.success("Re-indexing queued"),
                            onError: (e) => toast.error(errorMessage(e)),
                          })
                        }
                      >
                        <RefreshCwIcon />
                      </Button>
                      {canDelete && (
                        <ConfirmDialog
                          title={`Delete ${doc.original_filename}?`}
                          description="The file and its search index are removed. Agents will no longer use it."
                          onConfirm={() =>
                            remove.mutate(doc.id, {
                              onSuccess: () => toast.success("Document deleted"),
                              onError: (e) => toast.error(errorMessage(e)),
                            })
                          }
                          trigger={
                            <Button variant="ghost" size="icon" title="Delete" aria-label={`Delete ${doc.original_filename}`}>
                              <Trash2Icon />
                            </Button>
                          }
                        />
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  )
}
