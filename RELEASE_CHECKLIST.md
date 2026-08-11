# GitHub release checklist

- [x] Confirm the repository name `rdmr-pli-stm32`.
- [x] Apply MIT to software and CC BY 4.0 to data, figures, and documentation.
- [x] Exclude the frozen four-page EI working draft and remove its direct dependency from public audit scripts.
- [x] Recheck current CSSP policy concerning public preprints/repositories immediately before publication (2026-08-11; public code/data release passed with conditions).
- [x] Create the private GitHub repository and record its exact URL.
- [x] Push the verified candidate commit to the private repository.
- [x] Run the compact-package commands in `docs/reproducibility.md` from a clean clone.
- [x] Run the sensitive-string and absolute-path scan.
- [x] Rebuild `SHA256SUMS.txt` and verify every entry.
- [x] Add the private repository URL to `CITATION.cff` and `release-manifest.json`.
- [x] Record the canonical GitHub locator in the candidate manuscript availability statements.
- [ ] Optionally archive a tagged GitHub release in a DOI-granting repository and add that DOI.
- [x] Obtain final author approval before changing repository visibility to public (2026-08-11).
- [ ] Change repository visibility to public and verify logged-out access.
- [ ] Verify the official CSSP submission route; the current Editorial Manager page warns against live submission.
