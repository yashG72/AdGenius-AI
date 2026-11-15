"use client"

import { MusicIcon, PencilIcon, PlusIcon, Trash2Icon, UserPenIcon } from "lucide-react"
import { useEffect, useState } from "react"
import { useFieldArray, useForm } from "react-hook-form"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { errorMessage } from "@/lib/api/errors"
import type { Script } from "@/lib/api/types"
import { useOutput, useSaveOutput } from "@/lib/queries/campaigns"

import { VersionPicker } from "./version-picker"

type SceneValues = {
  duration_seconds: number
  visual_summary: string
  voiceover: string
  on_screen_text: string
  sound: string
}
type Values = {
  title: string
  opening_hook: string
  call_to_action: string
  music_suggestion: string
  scenes: SceneValues[]
}

function toValues(script: Script): Values {
  return {
    title: script.title,
    opening_hook: script.opening_hook,
    call_to_action: script.call_to_action,
    music_suggestion: script.music_suggestion ?? "",
    scenes: script.scenes.map((s) => ({
      duration_seconds: s.duration_seconds,
      visual_summary: s.visual_summary,
      voiceover: s.voiceover ?? "",
      on_screen_text: s.on_screen_text ?? "",
      sound: s.sound ?? "",
    })),
  }
}

export function ScriptEditor({ runId, editable }: { runId: string; editable: boolean }) {
  const latest = useOutput(runId, "script")
  const [version, setVersion] = useState<number | undefined>()
  const selected = useOutput(runId, "script", { version, enabled: version !== undefined })
  const output = version === undefined ? latest.data : selected.data
  const script = output?.content as Script | undefined
  const isLatest = !!output && output.version === latest.data?.versions
  const [editing, setEditing] = useState(false)
  const save = useSaveOutput(runId)

  const form = useForm<Values>()
  const scenes = useFieldArray({ control: form.control, name: "scenes" })
  useEffect(() => {
    if (script) form.reset(toValues(script))
  }, [script, form])

  if (latest.isPending) return <Skeleton className="h-96 rounded-xl" />
  if (!script || !output) return <p className="text-sm text-muted-foreground">No script yet.</p>

  const onSave = form.handleSubmit(async (v) => {
    const original = script.scenes
    const body: Script = {
      ...script,
      title: v.title,
      opening_hook: v.opening_hook,
      call_to_action: v.call_to_action,
      music_suggestion: v.music_suggestion,
      scenes: v.scenes.map((s, i) => ({
        ...(original[i] ?? { dialogue: [] }), // keep fields the editor doesn't expose (dialogue)
        scene_number: i + 1,
        start_time: 0,
        end_time: 0,
        duration_seconds: Number(s.duration_seconds) || 1,
        visual_summary: s.visual_summary,
        voiceover: s.voiceover,
        on_screen_text: s.on_screen_text,
        sound: s.sound,
      })),
    }
    try {
      const saved = await save.script.mutateAsync(body)
      toast.success(`Saved as version ${saved.version}${saved.content.timing_adjusted ? " — timings adjusted to the brief's duration" : ""}`)
      setEditing(false)
      setVersion(undefined)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  })

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2">
            {script.title}
            {output.source === "human" && (
              <Badge variant="secondary" className="gap-1">
                <UserPenIcon className="size-3" aria-hidden /> Edited
              </Badge>
            )}
          </CardTitle>
          <CardDescription>
            {script.duration_seconds}s · {script.scenes.length} scenes
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
      <CardContent>
        {!editing ? (
          <div className="space-y-4">
            <div className="rounded-lg bg-muted/50 p-3 text-sm">
              <span className="text-muted-foreground">Opening hook:</span> {script.opening_hook}
            </div>
            <ol className="space-y-3">
              {script.scenes.map((s) => (
                <li key={s.scene_number} className="grid gap-3 rounded-lg border border-border p-4 md:grid-cols-[90px_1fr_1fr]">
                  <div>
                    <p className="font-medium">Scene {s.scene_number}</p>
                    <p className="text-xs tabular-nums text-muted-foreground">
                      {s.start_time}–{s.end_time}s
                    </p>
                  </div>
                  <div className="space-y-1 text-sm">
                    <p className="text-xs text-muted-foreground">Visual</p>
                    <p>{s.visual_summary}</p>
                  </div>
                  <div className="space-y-2 text-sm">
                    {s.voiceover && (
                      <p><span className="text-xs text-muted-foreground">VO </span>{s.voiceover}</p>
                    )}
                    {(s.dialogue ?? []).map((d, i) => (
                      <p key={i}><span className="text-xs text-muted-foreground">{d.speaker} </span>{d.line}</p>
                    ))}
                    {s.on_screen_text && (
                      <p><span className="text-xs text-muted-foreground">TEXT </span><span className="font-medium">{s.on_screen_text}</span></p>
                    )}
                    {s.sound && <p className="text-xs text-muted-foreground">♪ {s.sound}</p>}
                  </div>
                </li>
              ))}
            </ol>
            <div className="grid gap-3 text-sm md:grid-cols-2">
              <p className="flex gap-2"><MusicIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />{script.music_suggestion || "—"}</p>
              <p><span className="text-muted-foreground">Call to action:</span> <span className="font-medium">{script.call_to_action}</span></p>
            </div>
          </div>
        ) : (
          <form onSubmit={onSave} className="space-y-4" noValidate>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1.5"><Label htmlFor="s-title">Title</Label><Input id="s-title" {...form.register("title", { required: true })} /></div>
              <div className="space-y-1.5"><Label htmlFor="s-cta">Call to action</Label><Input id="s-cta" {...form.register("call_to_action", { required: true })} /></div>
              <div className="space-y-1.5 md:col-span-2"><Label htmlFor="s-hook">Opening hook</Label><Textarea id="s-hook" rows={2} {...form.register("opening_hook", { required: true })} /></div>
            </div>
            {scenes.fields.map((field, i) => (
              <fieldset key={field.id} className="space-y-3 rounded-lg border border-border p-4">
                <div className="flex items-center justify-between">
                  <legend className="font-medium">Scene {i + 1}</legend>
                  <div className="flex items-center gap-2">
                    <Label htmlFor={`d-${i}`} className="text-xs text-muted-foreground">Seconds</Label>
                    <Input id={`d-${i}`} type="number" step="0.5" min="0.5" className="h-8 w-20" {...form.register(`scenes.${i}.duration_seconds`, { valueAsNumber: true })} />
                    <Button type="button" size="icon" variant="ghost" disabled={scenes.fields.length === 1} onClick={() => scenes.remove(i)} aria-label={`Remove scene ${i + 1}`}>
                      <Trash2Icon />
                    </Button>
                  </div>
                </div>
                <Textarea rows={2} placeholder="Visual" aria-label={`Scene ${i + 1} visual`} {...form.register(`scenes.${i}.visual_summary`, { required: true })} />
                <Textarea rows={2} placeholder="Voiceover" aria-label={`Scene ${i + 1} voiceover`} {...form.register(`scenes.${i}.voiceover`)} />
                <div className="grid gap-3 md:grid-cols-2">
                  <Input placeholder="On-screen text" aria-label={`Scene ${i + 1} on-screen text`} {...form.register(`scenes.${i}.on_screen_text`)} />
                  <Input placeholder="Sound / music cue" aria-label={`Scene ${i + 1} sound`} {...form.register(`scenes.${i}.sound`)} />
                </div>
              </fieldset>
            ))}
            <Button type="button" variant="outline" size="sm" onClick={() => scenes.append({ duration_seconds: 3, visual_summary: "", voiceover: "", on_screen_text: "", sound: "" })}>
              <PlusIcon /> Add scene
            </Button>
            <div className="space-y-1.5"><Label htmlFor="s-music">Music</Label><Input id="s-music" {...form.register("music_suggestion")} /></div>
            <p className="text-xs text-muted-foreground">Scene lengths are rescaled to the brief&apos;s total duration when you save. The previous version is kept.</p>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => { setEditing(false); form.reset(toValues(script)) }}>Cancel</Button>
              <Button type="submit" disabled={save.script.isPending}>{save.script.isPending ? "Saving…" : "Save as new version"}</Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  )
}
