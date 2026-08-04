# GitHub release checklist

- [x] Confirm the repository name `rdmr-pli-stm32`.
- [x] Apply MIT to software and CC BY 4.0 to data, figures, and documentation.
- [x] Exclude the frozen four-page EI working draft and remove its direct dependency from public audit scripts.
- [ ] Recheck current CSSP policy concerning public preprints/repositories immediately before publication.
- [x] Create the private GitHub repository and record its exact URL.
- [ ] Push the verified candidate commit to the private repository.
- [ ] Run all commands in `docs/reproducibility.md` from a clean clone.
- [ ] Run the sensitive-string and absolute-path scan.
- [ ] Rebuild `SHA256SUMS.txt` and verify every entry.
- [x] Add the private repository URL to `CITATION.cff` and `release-manifest.json`.
- [ ] Replace the manuscript placeholder `[PUBLIC REPOSITORY URL OR DOI]`.
- [ ] Optionally archive a tagged GitHub release in a DOI-granting repository and add that DOI.
- [ ] Obtain final author approval before changing repository visibility to public.
