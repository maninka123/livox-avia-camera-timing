# Interface readability and bounded previews

Main interface text and controls use 16 px at the default browser setting. Supporting text uses 14–15 px, section headings 22 px, and existing display/metric sizes retain their hierarchy. The scale uses rem units so browser text-size preferences reflow the layout. Scientific figure files and their font sizes were not changed.

The residual correlation matrix is displayed at a maximum width of 44 rem (704 px at the default size). Other plot widths are retained. Long per-capture scan traces use a keyboard-accessible panel capped at the smaller of 45 rem or 75% of the viewport height. Plot captions provide links to original-resolution images. Newly generated standalone HTML reports also use the compact matrix layout.

Individual scan previews stream the requested rows from the compressed point array in chunks of at most 1 MiB, rather than allocating all points in a recording. Preview reads are serialized independently of job/status handling. Processing jobs already run one at a time and folders process their bags sequentially. This reduces preview memory demand; it does not establish the cause of an earlier WSL crash or guarantee system-wide stability.

Verified:

- Workspace, saved library, single-bag overview/scans, and folder timing at widths 1512, 768, 390 and 320 px: no page overflow or browser script errors. Main interface text is at least 14 px, excluding the decorative brand subtitle.
- Workspace with 200% root text size at 1512, 390 and 320 px: no horizontal page overflow.
- Compact matrix width exactly 704 px on desktop; original PNG link responds successfully.
- Long trace panel height 720 px versus a 1,944 px image; keyboard scrolling works.
- C-/Fortran-ordered arrays, both float32/float64, empty scans, legacy metadata, invalid indices and invalid offsets tested. A real streamed scan matches saved point counts and depth STD.
- The real scan retained 4,819 returns (75.3 KiB) from a 30.0 MiB recording array. A separate read measured 4.6 MiB peak RSS growth; the 1 MiB bound applies to stream buffers, not total process memory.
- 56 software tests passed. No bag detection or timing processing was rerun for these presentation changes. Existing scientific results and figures are preserved.

[Browser checks](evidence/readability-verification/check_results.json) · [Figure checks](evidence/readability-verification/figure_checks.json) · [Memory measurement](evidence/readability-verification/memory_check.json) · [Software checks](evidence/readability-verification/software_checks.log)
