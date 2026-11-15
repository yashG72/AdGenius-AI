"use client"

import { CopyIcon, PencilIcon, UserPenIcon } from "lucide-react"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { errorMessage } from "@/lib/api/errors"
import type { Storyboard } from "@/lib/api/types"
import { useOutput, useSaveOutput } from "@/lib/queries/campaigns"

import { VersionPicker } from "./version-picker"

const TEXT_FIELDS = [
  ["scene_description", "Description"],
  ["visual_direction", "Visual direction"],
  ["composition", "Composition"],
  ["camera_angle", "Camera angle"],
  ["camera_movement", "Camera movement"],
  ["lighting", "Lighting"],
  ["voiceover", "Voiceover"],
  ["on_screen_text", "On-screen text"],
  ["transition", "Transition"],
] as const
type TextField = (typeof TEXT_FIELDS)[number][0]

type SceneValues = Record<TextField, string> & { prompt: string; negative_prompt: string }
type Values = { visual_style: string; consistency_notes: string; scenes: SceneValues[] }

function toValues(board: Storyboard): Values {
  return {
    visual_style: board.visual_style,
    consistency_notes: board.consistency_notes,
    scenes: board.scenes.map((s) => ({
      scene_description: s.scene_description,
      visual_direction: s.visual_direction,
      composition: s.composition ?? "",
      camera_angle: s.camera_angle,
      camera_movement: s.camera_movement,
      lighting: s.lighting,
      voiceover: s.voiceover ?? "",
      on_screen_text: s.on_screen_text ?? "",
      transition: s.transition,
      prompt: s.image_prompt.prompt,
      negative_prompt: s.image_prompt.negative_prompt ?? "",
    })),
  }
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success("Prompt copied")
  } catch {
    toast.error("Couldn't access the clipboard")
  }
}

export function StoryboardEditor({ runId, editable }: { runId: string; editable: boolean }) {
  const latest = useOutput(runId, "storyboard")
  const [version, setVersion] = useState<number | undefined>()
  const selected = useOutput(runId, "storyboard", { version, enabled: version !== undefined })
  const output = version === undefined ? latest.data : selected.data
  const board = output?.content as Storyboard | undefined
  const isLatest = !!output && output.version === latest.data?.versions
  const [editing, setEditing] = useState(false)
  const save = useSaveOutput(runId)
  const form = useForm<Values>()
  useEffect(() => {
    if (board) form.reset(toValues(board))
  }, [board, form])

  if (latest.isPending) return <Skeleton className="h-96 rounded-xl" />
  if (!board || !output) return <p className="text-sm text-muted-foreground">No storyboard yet.</p>

  const onSave = form.handleSubmit(async (v) => {
    const body: Storyboard = {
      ...board,
      visual_style: v.visual_style,
      consistency_notes: v.consistency_notes,
      scenes: board.scenes.map((scene, i) => {
        const edited = v.scenes[i]!
        return {
          ...scene,
          scene_description: edited.scene_description,
          visual_direction: edited.visual_direction,
          composition: edited.composition,
          camera_angle: edited.camera_angle,
          camera_movement: edited.camera_movement,
          lighting: edited.lighting,
          voiceover: edited.voiceover,
          on_screen_text: edited.on_screen_text,
          transition: edited.transition,
          image_prompt: { ...scene.image_prompt, prompt: edited.prompt, negative_prompt: edited.negative_prompt },
        }
      }),
    }
    try {
      const saved = await save.storyboard.mutateAsync(body)
      toast.success(`Saved as version ${saved.version}`)
      setEditing(false)
      setVersion(undefined)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  })

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2">
              Storyboard
              {output.source === "human" && (
                <Badge variant="secondary" className="gap-1"><UserPenIcon className="size-3" aria-hidden /> Edited</Badge>
              )}
            </CardTitle>
            <CardDescription>
              {board.scenes.length} scenes · {board.total_duration_seconds}s · {board.scenes[0]?.image_prompt.aspect_ratio}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <VersionPicker
              versions={latest.data?.versions ?? 1}
              value={output.version}
              onChange={(v) => {
                setEditing(false)
                setVersion(v === latest.data?.versions ? undefined : v)
              }}
            />
            {editable && isLatest && !editing && (
              <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                <PencilIcon /> Edit
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 text-sm md:grid-cols-2">
          {editing ? (
            <>
              <div className="space-y-1.5"><Label htmlFor="b-style">Visual style</Label><Textarea id="b-style" rows={3} {...form.register("visual_style")} /></div>
              <div className="space-y-1.5"><Label htmlFor="b-consistency">Consistency notes</Label><Textarea id="b-consistency" rows={3} {...form.register("consistency_notes")} /></div>
            </>
          ) : (
            <>
              <p><span className="text-muted-foreground">Visual style:</span> {board.visual_style}</p>
              <p><span className="text-muted-foreground">Consistency:</span> {board.consistency_notes}</p>
            </>
          )}
        </CardContent>
      </Card>

      <form onSubmit={onSave} noValidate className="space-y-4">
        {board.scenes.map((scene, i) => (
          <Card key={scene.scene_number}>
            <CardHeader>
              <CardTitle className="flex items-baseline gap-2 text-base">
                Scene {scene.scene_number}
                <span className="text-xs font-normal tabular-nums text-muted-foreground">
                  {scene.start_time}–{scene.end_time}s · {scene.duration_seconds}s
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-5 lg:grid-cols-[1fr_1fr]">
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                {TEXT_FIELDS.map(([key, label]) => (
                  <div key={key} className={key === "scene_description" || key === "visual_direction" ? "sm:col-span-2" : ""}>
                    <dt className="text-xs text-muted-foreground">{label}</dt>
                    <dd>
                      {editing ? (
                        key === "scene_description" || key === "visual_direction" ? (
                          <Textarea rows={2} aria-label={`Scene ${i + 1} ${label}`} {...form.register(`scenes.${i}.${key}`)} />
                        ) : (
                          <Input aria-label={`Scene ${i + 1} ${label}`} {...form.register(`scenes.${i}.${key}`)} />
                        )
                      ) : (
                        scene[key] || "—"
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
              <div className="space-y-3 rounded-lg bg-muted/40 p-4">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Image prompt</p>
                  <Button type="button" size="sm" variant="ghost" onClick={() => copy(scene.image_prompt.prompt)} aria-label={`Copy scene ${i + 1} prompt`}>
                    <CopyIcon /> Copy
                  </Button>
                </div>
                {editing ? (
                  <Textarea rows={6} aria-label={`Scene ${i + 1} image prompt`} {...form.register(`scenes.${i}.prompt`)} />
                ) : (
                  <p className="text-sm leading-relaxed">{scene.image_prompt.prompt}</p>
                )}
                <div>
                  <p className="text-xs text-muted-foreground">Negative prompt</p>
                  {editing ? (
                    <Input aria-label={`Scene ${i + 1} negative prompt`} {...form.register(`scenes.${i}.negative_prompt`)} />
                  ) : (
                    <p className="text-sm text-muted-foreground">{scene.image_prompt.negative_prompt || "—"}</p>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {scene.image_prompt.aspect_ratio} · {scene.image_prompt.camera_perspective} · {scene.image_prompt.lighting}
                </p>
              </div>
            </CardContent>
          </Card>
        ))}
        {editing && (
          <div className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-background/90 py-3 backdrop-blur">
            <Button type="button" variant="ghost" onClick={() => { setEditing(false); form.reset(toValues(board)) }}>Cancel</Button>
            <Button type="submit" disabled={save.storyboard.isPending}>{save.storyboard.isPending ? "Saving…" : "Save as new version"}</Button>
          </div>
        )}
      </form>
    </div>
  )
}
