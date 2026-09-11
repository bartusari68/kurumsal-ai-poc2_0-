# Project collaboration

- Preserve completed phases and real records. This is a desktop web application;
  do not spend phase work on mobile layouts.
- After each user-requested phase is implemented and its relevant regression checks
  pass, commit and push the completed changes to the configured GitHub origin.
  The user explicitly authorized this ongoing phase-end publishing workflow.
- Include pending changes from earlier phases when synchronizing an accumulated
  local checkout; do not discard or reset them. Explain the accumulated scope in
  the commit rather than claiming separate historical commits that did not occur.
- From Faz 13 onward, the user's latest publishing scope excludes generated,
  temporary and test-run artifacts. Stage reviewed source, source tests, assets and
  documentation explicitly. Do not stage live databases, backups, logs, caches,
  screenshots or generated fixtures. Preserve previously tracked comparison files
  and the existing lossless Git LFS packaging; do not delete them to clean history.
- Never overwrite the application's live database for publication. Keep environment
  secrets and virtual environments excluded. Do not use an unrestricted git add-all.
- Use normal history-preserving pushes. Inspect remote divergence before changing
  history, and verify the remote commit after upload. Do not claim upload success
  until Git confirms it. For large uploads, report each additional 500 MB.
