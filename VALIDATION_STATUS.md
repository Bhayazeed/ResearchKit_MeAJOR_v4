# Validation status

## Observed Open WebUI wrapper response (2026-10-28)

- The user's saved synthetic test response contains an executed `server:pplxdeciderflash/classify_with_pplx_decider` tool result. The initial parser incorrectly required a systemone operation name and nested question arguments, so it rejected this successful call.
- Added exact support for the observed flat state/instructions/criteria arguments and `answers.decision`. Only the question key is normalized to department/quality; model choices and scores are preserved. Raw tool-result hashes retain provenance before normalization. Altered inputs, missing execution evidence and ambiguous results still fail.
- The saved tool result selects technical, probability 0.9991184698158921, confidence 0.9986777047238382. These are results from the user's server response, not a locally inferred answer. The saved response now passes the complete smoke-test flow when replayed offline.
- 35 tests passed, including a fixture from the observed server tool metadata and rejection cases. Evidence: `tests/fixtures/openwebui_pplx_wrapped.json` and `outputs/review_20261028/tests_decider_wrapper.txt`. No new authenticated request or full remote curation was run by the assistant during this repair.

## Open WebUI PPLX transport and resume (2026-10-28)

- Added the user's example transport: `https://llms.si-lab.org/api/chat/completions`, `openai/gpt-oss-120b`, `server:pplxdeciderflash`, legacy function calling. Only structured server tool results with matching state/questions are accepted; chat prose is never used as a decision fallback.
- `RUN_CURATE_PPLX_OPENWEBUI.ps1` reads the API key from a hidden prompt or `OPENWEBUI_API_KEY`, runs the synthetic department-routing test first, then resumes label-1 English/length curation in a separate output directory. It does not change baseline victim endpoints.
- The user confirmed that old and new routes use the same PPLX backend. Checkpoint import records this as operator confirmation, preserves original annotation provider/model, validates source/policy/hash, and freezes the imported snapshot. This is not independent verification of model weights/version identity. A separate precheck-only import and direct authenticated endpoint option are available.
- Transient connection reset, timeout and selected HTTP errors retry with bounded backoff. Authentication failures stop; exhausted errors never become quality rejections. No bearer credential is written to manifests or CLI arguments.
- 31 offline tests passed, including exact tool-result extraction, rejecting changed input/chat-only results, label filtering, retry, and both checkpoint import modes. Evidence: `outputs/review_20261028/tests_decider_api.txt`.
- A read-only checkpoint snapshot contained 43,324 rows, all matching source label-1 IDs and hashes (20,347 local length rejections and 22,977 model decisions). This was a point-in-time check, not a statement of final completion. Evidence: `outputs/review_20261028/label1_checkpoint_check.json`.
- Live authenticated Open WebUI testing has not run: no key was supplied to this session. No department choice/probability or full remote-curation success is claimed. Server tool metadata/schema compatibility remains to be confirmed by the synthetic smoke test.

## Corrected curator/victim roles (2026-10-27)

- Supersedes the strict-curation proposal below. The active policy is `english_length`: code checks more than 100 alphabetic body words (minimum 101); the decision model checks English only. No phishing, legitimacy, reputation, or separate readability gate is used. No langdetect score threshold is applied.
- PPLX and chat LLMs classify PHISHING/NON_PHISHING only in their victim role. Original dataset labels remain unchanged. A victim NON_PHISHING result stays in the evaluation.
- Launchers, baseline input guards, downstream defaults and documentation now use the English/length v3 accepted dataset and its separate baseline output directory. Historical curation files remain unchanged; their acceptance flags are not silently converted to the new policy.
- All 19 offline tests passed, including the exact 100/101 boundary, body-only counting, English rejection, resume/manifest integrity and an accepted row later predicted NON_PHISHING by the victim. Model responses are mocked. Evidence: `outputs/review_20261027/tests_english_length.txt`.
- No full corrected curation or production victim inference has been executed. The final accepted count and live-model behavior under this policy remain unverified.

## Superseded strict curation and shared classification (2026-10-27)

- Active model labels are PHISHING/NON_PHISHING. Chat and decision models use shared definitions; decision probabilities use the PHISHING key. Old task aliases were removed from active Python classification/data parsing code. Classification instructions/criteria are hashed in baseline manifests.
- New curation enforces at least 100 body words, English score >=0.90, and model-screened phishing evidence. Rejection reasons and policy thresholds are exported. The subject does not count toward the minimum. A link/placeholder alone does not establish phishing.
- Baseline launchers and downstream dataset defaults point to the new strict accepted CSV. Baseline guards reject historical readability-only rows as inputs to the strict workflow. Optional freezing preserves primary audit annotations.
- Historical PPLX output is retained. The 31,056 old accepted rows include 12,998 below 100 body words; they cannot be represented as already passing the new policy.
- Tests use mocked model decisions and synthetic neutral text to exercise gates, exact word boundary, language failure, semantic rejection, resumed processing, manifest drift, shared classification payloads, probability mapping, and the curated-to-baseline-to-metrics handoff. No attacker generation was added.
- Full strict curation and production baseline inference have not been executed. The accepted count under the new policy is not yet known. Existing readability evidence is historical, not a strict-policy result.
- Final checks: 19 tests passed; Python compilation succeeded; no old task label strings remain in active `phishbench`, `scripts`, or `config` code. The local PPLX endpoint at port 11435 refused the connection during the 2026-10-27 availability check, so no new live curation was started. Test log and legacy input checks are in `outputs/review_20261027`.

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
