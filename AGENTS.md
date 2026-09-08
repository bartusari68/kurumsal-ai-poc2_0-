# Project collaboration

- Preserve completed phases and real records. This is a desktop web application;
  do not spend phase work on mobile layouts.
- After each user-requested phase is implemented and its relevant regression checks
  pass, commit and push the completed changes to the configured GitHub origin.
  The user explicitly authorized this ongoing phase-end publishing workflow.
- Include pending changes from earlier phases when synchronizing an accumulated
  local checkout; do not discard or reset them. Explain the accumulated scope in
  the commit rather than claiming separate historical commits that did not occur.
- The comparison repository intentionally includes the complete project, database,
  PDFs, model transfer parts, tests and supporting files. Exclude environment secrets
  and virtual environments. Keep the existing lossless Git LFS model packaging.
- Stage a consistent SQLite backup in the Git index for the live database; never
  overwrite the application's database just to publish a snapshot.
- Use normal history-preserving pushes. Inspect remote divergence before changing
  history, and verify the remote commit after upload. Do not claim upload success
  until Git confirms it. For large uploads, report each additional 500 MB.
