---
applyTo: "**"
---

# Agent Instructions

## Project Context

Before starting any task, read `CLAUDE.md` in the repository root for full project instructions, including module map, data models, anti-patterns, and key constraints.

## Changelog Rule

Every time you make a code change (add, modify, or delete files), you MUST append a log entry to `CHANGELOG.md` under the current version section.

Format:
- Use `### Added` / `### Changed` / `### Fixed` / `### Removed` subsections as appropriate
- Each entry should be a concise one-line bullet describing what was done
- If a new version is started, add a new `## [x.x.x] - YYYY-MM-DD` header

Do NOT skip this step. Update the changelog as part of the same operation.
