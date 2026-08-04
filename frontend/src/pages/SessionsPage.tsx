import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { sessionApi } from "@/lib/sessionApi"
import type { SessionManifest } from "@/lib/types"

/** Session list + create -- the entry point into the session-centric
 * workflow control plane (Phase 4). Session id lives in the URL from here
 * on, so a page reload never loses context (Phase 1's stated goal). */
export function SessionsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [factorId, setFactorId] = useState("")

  const sessionsQuery = useQuery({ queryKey: ["sessions"], queryFn: sessionApi.list })

  const createMutation = useMutation({
    mutationFn: () => sessionApi.create(factorId),
    onSuccess: (manifest) => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
      navigate(`/sessions/${manifest.session_id}/steps/1`)
    },
  })

  return (
    <div className="flex flex-col gap-6 p-6">
      <Card>
        <CardHeader>
          <CardTitle>New session</CardTitle>
        </CardHeader>
        <CardContent className="flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="factor-id">Factor id</Label>
            <Input
              id="factor-id"
              value={factorId}
              onChange={(e) => setFactorId(e.target.value)}
              placeholder="cooper_gulen_schill_2008_asset_growth"
            />
          </div>
          <Button disabled={!factorId || createMutation.isPending} onClick={() => createMutation.mutate()}>
            Create session
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sessions</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Factor</TableHead>
                <TableHead>State</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(sessionsQuery.data ?? []).map((s) => (
                <SessionRow key={s.session_id} session={s} onNavigate={navigate} />
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}

function SessionRow({
  session,
  onNavigate,
}: {
  session: SessionManifest
  onNavigate: (path: string) => void
}) {
  const queryClient = useQueryClient()

  const archiveMutation = useMutation({
    mutationFn: () => sessionApi.archive(session.session_id, session.revision),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sessions"] }),
  })
  const deleteMutation = useMutation({
    mutationFn: () => sessionApi.hardDelete(session.session_id, session.revision),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sessions"] }),
  })

  return (
    <TableRow className="cursor-pointer" onClick={() => onNavigate(`/sessions/${session.session_id}/steps/1`)}>
      <TableCell>{session.factor_id}</TableCell>
      <TableCell>
        <Badge variant="outline">{session.state}</Badge>
      </TableCell>
      <TableCell>{new Date(session.created_at).toLocaleString()}</TableCell>
      <TableCell onClick={(e) => e.stopPropagation()}>
        <div className="flex gap-2">
          {session.state !== "archived" && (
            <Button size="sm" variant="outline" onClick={() => archiveMutation.mutate()}>
              Archive
            </Button>
          )}
          <Button
            size="sm"
            variant="destructive"
            onClick={() => {
              if (window.confirm(`Permanently delete session for '${session.factor_id}'? This cannot be undone.`)) {
                deleteMutation.mutate()
              }
            }}
          >
            Delete
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}
