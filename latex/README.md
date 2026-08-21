# Thesis LaTeX Source

Compile on Overleaf: upload this whole `latex/` folder as the project root
(or `zip` it and use "Upload Project"). `main.tex` is the root document.
The project uses the supplied `MastersDoctoralThesis.cls` and the original
UNIL logo under `Figures/`. Keep both when uploading the folder to Overleaf.

Local compile (if you have a LaTeX distribution installed):

```bash
cd latex
pdflatex main
bibtex main
pdflatex main
pdflatex main
```

## Structure

- `MastersDoctoralThesis.cls` — the supplied template's page, heading, spacing,
  caption, header, and footer definitions.
- `main.tex` — the supplied template's UNIL title page, abstract/front matter,
  and `\input`s for all content files.
- `preamble.tex` — packages and notation macros ($A$, $C_{cz}$, $C_{std}$,
  etc.); visual formatting remains in the supplied class.
- `Figures/UNIL-LOGOTYPE-BLUE-CMYK.eps` — original UNIL title-page logo.
- `sections/01_introduction.tex` … `08_discussion.tex` — the 8 chapters.
- `sections/appendix_a_*.tex` … `appendix_f_*.tex` — appendices A–F.
- `tables/*.tex` — one file per table (T1–T7 + two extra positioning/roster
  tables), `\input` from the relevant section. All placeholders (`TODO`)
  until real numbers are generated from `runs/backtest_scripts/results/`.
- `Figures/` — put exported F1–F4 here; sections currently reference `\fbox`
  placeholders.
- `refs.bib` — seed bibliography; verify page/figure numbers against the
  source PDFs before final submission.

## Formatting adaptation

The presentation now uses the supplied master's-thesis class directly rather
than approximating it: its exact A4 geometry, line spacing, heading hierarchy,
caption rules, page-count header, author/title footer, ruled title page, UNIL
logo placement, and BibLaTeX author-year bibliography style. The files under
`sections/` and `tables/`, together with `refs.bib`, remain content-only and
were not rewritten. Their heading levels are promoted by `main.tex` when
typeset, so each existing top-level `\section` appears as a thesis chapter
without altering source text.

## Where the numbers come from

Every table's source is documented in a comment at the top of its `.tex`
file (e.g. `comparison.json: gap_decomposition`, `.metrics.json`). See
`docs/paper-outline.md` for the full discussion history, the six-factor
selection rationale (§5.3), and the scope/assumptions this thesis is built
on (§4). Do not hand-type numbers into these tables without a corresponding
JSON source — consider building `scripts/export_paper_tables.py` (discussed,
not yet implemented) to generate table bodies directly from
`comparison.json` once the six factors have been run.

## Known open items (see docs/paper-outline.md for detail)

- The 6 factors are: `AssetGrowth` (already run), `GP`, `PS`, `BrandInvest`,
  `OperProfRD`, `grcapx3y`. The latter 5 still need: field registration in
  `src/infra/data_layer/sources.py` (`xad`, `fyr`, `sic`, `ppent`, `oancf`,
  `txt` — all confirmed present in the raw local CSV, so mechanical, not
  blocked) and MethodSpec extraction + review.
- `PS` requires a declared `accepted_unapplied` deviation (BM-quintile
  filter is not implementable).
- `grcapx3y`'s sample window (1976–1999) may not support the
  post-publication decay test — verify before running.
- WRDS vintage / sample coverage must be documented manually in Appendix F
  once the actual data pull is finalized.
