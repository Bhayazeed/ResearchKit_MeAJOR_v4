# Validation status

## Label-1 pipeline review (2026-10-26)

- Status: needs methodological revision before paper claims; the label-1 CSV path and completed PPLX output were independently reconciled.
- Local source MD5 matches the official Zenodo CSV. All 48,034 PPLX audit IDs, text hashes, labels and all 20 source metadata fields match the selected source records. Accepted export and checkpoint ID sets reconcile: 31,056 usable, 16,978 not usable. Existing curation files were not regenerated or changed during review.
- Positive input includes 46,842 distinct normalized texts and 1,192 duplicate excess records. No conflicting binary labels were found among exact normalized text hashes. Near-duplicates and semantic correctness have not been verified.
- Label-1 freeze now keeps every commonly accepted row by default, with provenance checks; an optional `--per-class` remains for explicitly requested sampling. Quality comparisons now check hashes and labels. Baseline metrics now disclose class support, coverage and conditional versus all-positive denominators. Checkpoint loading now rejects committed corruption/duplicate IDs and recovers only a torn final write.
- Windows baseline dry-run selects 48,034 rows. This is a plan, not completed inference. Local service check on this date: port 11434 responds but configured Qwen3.5:9B and Gemma4:E4B tags are absent; port 11435 refuses the connection. Historical PPLX output is still intact and does not establish current service availability.
- Remaining issues: align chat/decision class definitions, pin model digests and inference settings, choose full versus curated analysis population, independently validate curation, account for duplicates/language, and specify confidence intervals. The active protocol records these limits. OpenRouter, live baseline models and optional SBERT evaluation were not exercised in this review.
- Evidence: `outputs/review_20261026/data_verification.json`, companion verification script, and the regression tests in `tests/test_research_pipeline.py`.
- Final verification: 14 regression tests passed and compilation succeeded. The freeze integration check produced 31,056 label-1 rows with exactly the same IDs and text hashes as the existing PPLX accepted export; the check's output is isolated at `outputs/review_20261026/freeze_validation.csv` and is not a newly selected primary experiment cohort.

## Full-dataset support (2026-10-24)

- Raw MeAJOR input now works directly for curation, baseline, and downstream dataset readers. Curation/baseline launchers default to the full CSV; sampling launchers remain optional.
- Loaded all 108,685 original rows and verified 108,685 unique row IDs: 60,650 label-0, 48,034 label-1, and 1 invalid label retained with the original value in `meajor_label`.
- Six offline tests passed, covering raw duplicates, empty/non-English text, metadata preservation, invalid-label metrics, actual langdetect, interruption/resume, source-manifest mismatch, mocked baseline calls, and existing prepared-cohort compatibility.
- Python compilation passed. Full-dataset baseline dry run planned all 108,685 rows for the five enabled models.
- One real local PPLX System-One request using synthetic email text succeeded (`usable`). This verifies connectivity and response parsing, not full-dataset completion or classification accuracy.
- The complete PPLX/langdetect/JEV curation and full baseline model runs have not been executed. OpenRouter and other live baseline models remain untested in this update.

## Previous validation (2026-10-21)

- Parsed and audited the entire bundled 108,685-row original MeAJOR CSV (60,650 label-0, 48,034 label-1, 1 invalid label; only TREC5/6/7 source tags).
- Python compileall passed; 2 synthetic offline unit tests passed.
- Successfully prepared and inspected 10 samples using explicit `--language-mode supplied` fallback (which uses the source `language` field, NOT actual langdetect); these smoke records are NOT included as reportable research results.
- Baseline chat and decision-model API requests, metadata subgroup reporting and checkpoint/resume were tested using a local simulated HTTP server; no real Ollama classification was executed.
- `langdetect` could not be installed in this sandbox due to unavailable network access; the default `--language-mode langdetect` is not end-to-end tested. Install dependency before running for real.
- OpenRouter JEV API, PPLX Ollama actual models, OpenAttack GAN and Qwen rewriting are NOT live tested. GAN/Qwen phishing-evasion generation is intentionally not implemented; only retrospective reviewed-candidate analysis is supported.
- No substantive accuracy or adversarial success claims should be inferred from these tests.
