# Research Kit v4 — MeAJOR (2026), defensive email detector robustness

**Primary dataset: MeAJOR** (Cardoso et al. 2026), **not Alhuzali**. Bundles the provided `data/meajor_cleaned_preprocessed.csv` (191 MB). The curation and baseline launchers use **all 48,034 rows with label 1** from the original CSV directly, without preparing a sample. Original metadata is retained as `meajor_*`; classification uses **subject + body**. Optional sample preparation still supports pilot (500 + 500) and main (1500 + 1500) cohorts. Label 1 is the dataset's phishing class but may contain spam examples.

### Install

Python 3.10+ and `pip install -r requirements.txt` (langdetect). Analytical metrics: `pip install -r requirements-analysis.txt` (SBERT may download a model). Ollama models are optional and only needed for baseline / local PPLX quality. JEV requires OpenRouter API key and deliberate third-party data-sharing permission.

### Commands (from project root)

```bash
python scripts/dataset_audit.py
python scripts/prepare_meajor.py --input data/meajor_cleaned_preprocessed.csv --output data/meajor_pilot_1000.csv --per-class 500
python scripts/prepare_meajor.py --input data/meajor_cleaned_preprocessed.csv --output data/meajor_main_3000.csv --per-class 1500
python scripts/curate_meajor.py --input data/meajor_cleaned_preprocessed.csv --output-dir outputs/quality_langdetect_label1 --provider langdetect
python scripts/curate_meajor.py --input data/meajor_cleaned_preprocessed.csv --output-dir outputs/quality_pplx_label1 --provider ollama --base-url http://127.0.0.1:11435 --model pplx-decider:latest
python scripts/curate_meajor.py --input data/meajor_cleaned_preprocessed.csv --output-dir outputs/quality_jev_label1 --provider openrouter --model typesafe/jev-1.14
python scripts/compare_curations.py --a outputs/quality_pplx_label1/quality_audit.csv --b outputs/quality_jev_label1/quality_audit.csv --output outputs/quality_agreement.csv
python scripts/run_baseline.py --input data/meajor_cleaned_preprocessed.csv --output-dir outputs/label1_baseline --dry-run
python scripts/run_baseline.py --input data/meajor_cleaned_preprocessed.csv --output-dir outputs/label1_baseline
python scripts/baseline_metrics.py --dataset data/meajor_cleaned_preprocessed.csv --dir outputs/label1_baseline --output outputs/label1_baseline/metrics.csv
```

### Run all label-1 rows on Windows

```powershell
.\RUN_CURATE_PPLX.bat
# Other independent runs:
.\RUN_CURATE_LANGDETECT.bat
.\RUN_CURATE_JEV.bat
.\RUN_BASELINE_DRY_RUN.bat
.\RUN_BASELINE.bat
```

No `RUN_PREPARE_*` step is required. All `RUN_CURATE_*` and `RUN_BASELINE*` launchers read `data/meajor_cleaned_preprocessed.csv` with `--label 1`. Label 0 and invalid labels are excluded before any model request. No sampling is performed. The `RUN_PREPARE_PILOT` and `RUN_PREPARE_MAIN` launchers remain optional sampling tools.

Curation, baseline, and downstream analysis commands default to `--label 1` for both raw and prepared input. Use `--label all` explicitly only when analyzing both classes. Every selected label-1 row is retained in source order, including duplicates, short/empty text, and non-English emails. Source indexes and row IDs remain stable after filtering; original fields are preserved as `meajor_*`. The audit CSV contains every selected row; `quality_accepted.csv` contains only accepted rows.

Label selection is part of each run manifest. Label-1 launchers use separate output directories so existing all-label checkpoints remain untouched. A process started before this change still uses its loaded code: stop it with Ctrl+C and restart the updated launcher to apply the filter.

For raw input, `CURATE_LANGDETECT` runs actual language detection (up to 6,000 characters per email); it does not simply trust the source language column. PPLX/JEV retain the existing 20,000-character request limit per email. These limits affect text per request, not the number of rows. PPLX uses the local System-One endpoint at `http://127.0.0.1:11435`; JEV needs an OpenRouter key and sends email text to that service. Label-1 baseline results go to `outputs/label1_baseline`.

Full runs may take a long time. Progress starts by printing the loaded row count, and completed rows are checkpointed individually. Rerun the same launcher to resume. If an output directory already contains a different dataset/model manifest, choose a new output directory; do not delete or mix checkpoints. Prepared cohort CSVs are still accepted by the Python commands.

Use supplied Windows `.bat` and Linux/macOS `.sh` launchers for the same actions. Each quality and baseline task has an append-only per-row JSONL checkpoint (resumed with unchanged settings/source). Curated outputs preserve original labels, accepted/rejected status, metadata, source, language score, placeholder statistics. No automatic label changes.

### Offline reviewed candidate comparison (GAN / Qwen method IDs)

Only if you already have permitted **reviewed offline** candidate texts, populate `templates/offline_candidates_template.csv` (required columns: `row_id,method,candidate_text,review_status,final_prediction`). Then:

```bash
python scripts/evaluate_candidates.py --dataset data/meajor_cleaned_preprocessed.csv --baseline outputs/label1_baseline/qwen35_9b_baseline.csv --candidates path/to/reviewed_candidates.csv --output-dir outputs/offline_review
python scripts/evaluate_similarity.py --dataset data/meajor_cleaned_preprocessed.csv --candidates path/to/reviewed_candidates.csv --output outputs/offline_review/similarity.csv --sbert
```

This v4 supplies **defensive evaluation and analysis**, not GAN attacks or Qwen phishing-evasion generation. `final_prediction` is a recorded prediction from an independently authorized evaluation; the script will not generate candidates or seek evasion. Do not interpret a flip as validated phishing attack success without human review of intent/semantics.

### Paper considerations

The active experiment includes label 1 only. Its primary detector measures are positive detection/recall and response coverage; single-class accuracy/precision/F1 must not be presented as representative two-class detector performance. `baseline_metrics.py` now records class support, metric scope and detection rate over all positives alongside the existing conditional metrics. See the active workflow and unresolved research-design issues in `docs/RESEARCH_PROTOCOL.md`.

Baseline launchers currently evaluate all 48,034 positives, independently of curation. For an explicitly chosen accepted-only analysis, `scripts/freeze_approved.py --label 1` can retain all commonly accepted rows when `--per-class` is omitted. Pass that frozen CSV to every baseline and downstream command in a separate output directory. Quality decisions are not human validation; selection by the same model later benchmarked requires sensitivity analysis.

The supplied CSV has sources `trec5`, `trec6`, `trec7` only, despite the paper's five-source description. Stratified and source-based reporting is supported. Keep the exact same frozen rows when comparing PPLX/JEV/other decisions; if using accepted-only cohorts, use `scripts/freeze_approved.py` on common audit outputs. See `docs/RESEARCH_PROTOCOL.md`.

MeAJOR: https://doi.org/10.5281/zenodo.18471483 (CC BY 4.0); Cardoso et al., *Data in Brief* (2026), https://doi.org/10.1016/j.dib.2026.112595.

### Metadata subgroup reporting

```bash
python scripts/analyze_metadata.py --dataset data/meajor_cleaned_preprocessed.csv --baseline outputs/label1_baseline/qwen35_9b_baseline.csv --output outputs/label1_baseline/qwen35_metadata.csv
```

Reports confusion matrices by source, placeholder presence, and length group; subgroup estimates are descriptive and require confidence intervals.
