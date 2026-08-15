import type { SessionManifest } from "@/lib/types"

/** Find the most recent SUCCESSFUL attempt's output_ref for `key` on `step`
 * -- shared by step4/5's "look at what an earlier step produced" needs
 * (e.g. step5 reading step3's resolved config/spec to get sample years and
 * the paper's own reported result). */
export function latestSuccessRef(
  manifest: SessionManifest | undefined,
  step: number,
  key: string,
): string | undefined {
  const attempts = manifest?.steps[String(step)]?.attempts ?? []
  for (let i = attempts.length - 1; i >= 0; i--) {
    const ref = attempts[i].output_refs[key]
    if (attempts[i].status === "success" && ref) return ref
  }
  return undefined
}
