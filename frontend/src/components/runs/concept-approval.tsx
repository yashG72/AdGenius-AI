"use client"

import { CheckIcon, UserCheckIcon, XIcon } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { errorMessage } from "@/lib/api/errors"
import type { Approval, Concept } from "@/lib/api/types"
import { useDecision } from "@/lib/queries/campaigns"

import { ConceptCard } from "./concept-card"

type Payload = {
  round: number
  concepts: Concept[]
  recommended_concept_id: string
  recommendation_reasoning: string
}

export function ConceptApproval({ runId, approval }: { runId: string; approval: Approval }) {
  const payload = approval.payload as unknown as Payload
  const [selected, setSelected] = useState(payload.recommended_concept_id)
  const [notes, setNotes] = useState("")
  const [rejecting, setRejecting] = useState(false)
  const [feedback, setFeedback] = useState("")
  const { approve, reject } = useDecision(runId)

  const onApprove = () =>
    approve.mutate(
      { approvalId: approval.id, conceptId: selected, feedback: notes.trim() || undefined },
      {
        onSuccess: () => toast.success(`${selected} approved — the Scriptwriter is starting`),
        onError: (e) => toast.error(errorMessage(e)),
      },
    )

  const onReject = () =>
    reject.mutate(
      { approvalId: approval.id, feedback: feedback.trim() },
      {
        onSuccess: () => {
          setRejecting(false)
          toast.success("Feedback sent — the Strategist is working on new concepts")
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    )

  return (
    <Card className="border-amber-500/40">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserCheckIcon className="size-4 text-amber-300" aria-hidden />
          Choose a concept {payload.round > 1 && <span className="text-sm font-normal text-muted-foreground">(round {payload.round})</span>}
        </CardTitle>
        <CardDescription>
          The agents paused for you. Pick the concept to produce, or reject them all with feedback for a new round.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 lg:grid-cols-3" role="group" aria-label="Concepts">
          {payload.concepts.map((concept) => (
            <ConceptCard
              key={concept.concept_id}
              concept={concept}
              recommended={concept.concept_id === payload.recommended_concept_id}
              selected={concept.concept_id === selected}
              onSelect={() => setSelected(concept.concept_id)}
            />
          ))}
        </div>
        <div className="rounded-lg bg-muted/50 p-4 text-sm">
          <span className="font-medium">Strategist&apos;s recommendation ({payload.recommended_concept_id}):</span>{" "}
          <span className="text-muted-foreground">{payload.recommendation_reasoning}</span>
        </div>
        <div className="space-y-2">
          <Label htmlFor="approval-notes">Notes for the production team (optional)</Label>
          <Textarea
            id="approval-notes"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g. keep the ending on the tagline, avoid exam-performance jokes"
          />
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={() => setRejecting(true)} disabled={approve.isPending}>
            <XIcon /> Reject all…
          </Button>
          <Button onClick={onApprove} disabled={approve.isPending || !selected}>
            <CheckIcon /> {approve.isPending ? "Approving…" : `Approve ${selected}`}
          </Button>
        </div>
      </CardContent>

      <Dialog open={rejecting} onOpenChange={setRejecting}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject these concepts?</DialogTitle>
            <DialogDescription>Tell the Creative Strategist what to change. It will produce a new set.</DialogDescription>
          </DialogHeader>
          <Textarea
            rows={4}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="More playful, less product talk, focus on hostel life…"
            aria-label="Feedback"
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRejecting(false)}>
              Cancel
            </Button>
            <Button onClick={onReject} disabled={!feedback.trim() || reject.isPending}>
              {reject.isPending ? "Sending…" : "Reject & regenerate"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
