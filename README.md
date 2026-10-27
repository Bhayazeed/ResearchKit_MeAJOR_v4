# Research Kit v4 — MeAJOR phishing classification

The active defensive workflow uses the original MeAJOR CSV, selects every **label-1** row without sampling, curates the examples, and classifies the accepted cohort with chat and decision models. Both model types use the same **PHISHING / NON_PHISHING** definitions in `phishbench/classification.py`. Original gold labels remain numeric 1/0 and are never overwritten by model predictions.

## Active flow

```text
Original MeAJOR CSV
  -> all 48,034 label-1 rows
  -> body has more than 100 alphabetic words (minimum 101)
  -> PPLX decision model checks only whether the body is English
  -> quality_accepted.csv, with IDs, hashes, metadata and rejection audit
  -> same accepted input for each chat/decision baseline
  -> detection/recall, response coverage and paired analysis
```

The curator does not judge phishing intent, legitimacy, link reputation, or readability as a separate criterion. PPLX acts as a language judge here; in the baseline it acts as a victim classifier with a different prompt. Eligibility never depends on a victim prediction. A later NON_PHISHING prediction remains in the evaluation with its original dataset label. Curator acceptance is not independent validation of phishing ground truth.

## Panduan pipeline: dari input sampai keluaran

Jalankan perintah dari folder utama project. Inputnya adalah **`data/meajor_cleaned_preprocessed.csv`**, bukan file Python. Adapter `phishbench/data.py` membaca CSV, membuat ID dan hash teks, serta mempertahankan metadata sumber. Adapter ini dipanggil oleh script, tidak perlu dijalankan sendiri.

```text
 data/meajor_cleaned_preprocessed.csv
       |
       +-- dataset_audit.py --> meajor_dataset_audit.json (audit seluruh CSV)
       |
       v
 curate_meajor.py --label 1 --policy english_length --min-words 101
       |
       +-- body <=100 kata --------> ditolak, tetap tercatat dalam audit
       +-- body >100 kata
               |
               v
          PPLX: apakah body berbahasa Inggris?
               +-- tidak ----------> ditolak, tetap tercatat dalam audit
               +-- ya
                    |
                    v
          quality_accepted.csv (cohort yang sama untuk semua victim)
                    |
          run_baseline.py --dry-run --> run_plan.csv
                    |
          run_baseline.py
                    +-- chat LLM: PHISHING / NON_PHISHING
                    +-- decision model, termasuk PPLX: PHISHING / NON_PHISHING
                    |
                    v
          <victim_id>_baseline.csv
                    +-- baseline_metrics.py --> metrics.csv (semua victim)
                    +-- analyze_metadata.py --> <victim_id>_metadata.csv
                    |
                    +-- opsional, jika kandidat dan prediksinya sudah tersedia:
                        evaluate_candidates.py --> laporan kandidat berpasangan
                        evaluate_similarity.py --> similarity.csv
```

### 1. Persiapan dan audit input

Gunakan Python 3.10+. Contoh PowerShell berikut memilih interpreter yang sama dengan launcher Windows:

```powershell
$PipelinePython = if (Test-Path '.venv/Scripts/python.exe') { '.venv/Scripts/python.exe' } else { 'python' }
& $PipelinePython -m pip install -r requirements.txt
.\RUN_AUDIT.bat
```

`RUN_AUDIT.bat` menjalankan `scripts/dataset_audit.py`. Hasilnya `outputs/meajor_dataset_audit.json`, berisi jumlah baris, label, sumber dan placeholder. Audit membaca seluruh CSV tanpa memanggil model atau memilih cohort. CSV yang sudah diperiksa berisi 108.685 baris; 48.034 memiliki label 1. Seleksi label 1 dilakukan pada tahap kurasi.

Sebelum inference, sediakan `pplx-decider:latest` pada endpoint decision `http://127.0.0.1:11435`. Periksa model victim yang diaktifkan di `config/models.json`. Chat menggunakan port 11434, decision menggunakan port 11435. Daftar konfigurasi bukan bukti model sudah tersedia di server.

### 2. Kurasi bahasa dan panjang

```powershell
.\RUN_CURATE_PPLX.bat
```

Launcher menjalankan `scripts/curate_meajor.py` dengan seluruh label 1, `--policy english_length` dan `--min-words 101`. Kode menghitung kata pada body; PPLX hanya menilai bahasa Inggris. Tidak ada sampling atau syarat harus diprediksi phishing pada tahap ini.

Keluaran berada di `outputs/quality_pplx_english_length_v3/`:

| File | Isi / kegunaan |
| --- | --- |
| `quality_audit.csv` | Semua baris label 1 dengan keputusan diterima/ditolak dan alasannya. |
| `quality_accepted.csv` | Semua baris yang lolos; menjadi input utama baseline dan analisis berikutnya. |
| `quality_summary.json` | Jumlah diperiksa, diterima, kategori keputusan dan alasan penolakan. |
| `quality_manifest.json` | Hash sumber, model, kebijakan, instruksi dan batas kata untuk validasi resume. |
| `quality_checkpoint.jsonl` | Keputusan per baris untuk melanjutkan proses yang terputus. |

CSV audit, accepted dan ringkasan diterbitkan setelah seluruh kurasi selesai. Jika proses terputus, perbaiki penyebabnya lalu jalankan perintah yang sama untuk melanjutkan dari checkpoint. Perubahan sumber, model atau kebijakan memerlukan direktori output baru. Jangan menggunakan hasil lama sebagai hasil kebijakan baru.

### 3. Periksa input baseline tanpa inference

```powershell
.\RUN_BASELINE_DRY_RUN.bat
```

Launcher memanggil `scripts/run_baseline.py --require-curated --dry-run`. Script membaca `quality_accepted.csv`, memeriksa anotasi kurasi, ID dan hash teks, lalu menulis `outputs/curated_english_length_baseline/run_plan.csv`. File ini mencatat victim dan jumlah baris yang direncanakan. Dry-run tidak menguji koneksi/model dan tidak menghasilkan prediksi.

### 4. Klasifikasi oleh seluruh victim yang aktif

```powershell
.\RUN_BASELINE.bat
```

Launcher memanggil `scripts/run_baseline.py --require-curated` dengan cohort yang sama. Konfigurasi saat ini mengaktifkan:

| Victim ID | Model tag | Jenis |
| --- | --- | --- |
| `qwen35_9b` | `qwen3.5:9b` | Chat LLM |
| `gemma4_e4b` | `gemma4:e4b` | Chat LLM |
| `pplx_decider` | `pplx-decider:latest` | Decision model |
| `nimble_9b` | `nimble:9b` | Decision model |
| `tev1_4b` | `tev1:4b` | Decision model |

Setiap victim menerima teks subject + body dan tugas PHISHING/NON_PHISHING yang sama. Prediksi disimpan sebagai `1`/`0`; `dataset_label` tetap mengikuti sumber. Prediksi NON_PHISHING tidak mengeluarkan baris dari cohort.

Keluaran di `outputs/curated_english_length_baseline/`:

- `<victim_id>_baseline.csv`: ID, hash, label sumber, prediksi, status/error, identitas model dan confidence/probabilitas jika tersedia.
- `<victim_id>_baseline.csv.run.json`: manifest sumber, konfigurasi dan hash instruksi klasifikasi.
- `<victim_id>_baseline.csv.checkpoint.jsonl`: hasil per baris untuk resume.
- `run_plan.csv`: rencana model dan jumlah baris, bukan bukti inference sudah selesai.

CSV baseline dapat berisi hasil parsial selama proses berlangsung. Tunggu seluruh victim yang dipilih selesai sebelum membuat laporan gabungan; script metrik akan menolak baseline yang jumlah/ID barisnya tidak cocok dengan cohort. Rerun dengan konfigurasi yang sama melanjutkan hasil yang sudah tersimpan, termasuk status nonrespons yang telah dicatat.

### 5. Buat metrik gabungan dan laporan metadata setiap victim

Jalankan setelah tahap 4 selesai, menggunakan interpreter dan dataset yang sama:

```powershell
$PipelinePython = if (Test-Path '.venv/Scripts/python.exe') { '.venv/Scripts/python.exe' } else { 'python' }
$CuratedDataset = 'outputs/quality_pplx_english_length_v3/quality_accepted.csv'
$BaselineDirectory = 'outputs/curated_english_length_baseline'

& $PipelinePython scripts/baseline_metrics.py --dataset $CuratedDataset --dir $BaselineDirectory --output "$BaselineDirectory/metrics.csv"

Get-ChildItem -LiteralPath $BaselineDirectory -Filter '*_baseline.csv' | ForEach-Object {
    $VictimId = $_.BaseName -replace '_baseline$', ''
    & $PipelinePython scripts/analyze_metadata.py --dataset $CuratedDataset --baseline $_.FullName --output "$BaselineDirectory/$($VictimId)_metadata.csv"
}
```

`metrics.csv` berisi satu baris per victim: TP/FN, recall, jumlah nonrespons, coverage, dan detection rate dengan seluruh positif sebagai denominator. File `<victim_id>_metadata.csv` merinci performa menurut sumber, keberadaan placeholder dan kelompok panjang teks. Karena cohort hanya label 1, hasil ini tidak mengukur false-positive rate pada email benign. Lihat bagian metrik di bawah untuk batas interpretasinya.

### 6. Tahap opsional dan hubungan antar-script

| Script / launcher | Input | Keluaran / kapan digunakan |
| --- | --- | --- |
| `RUN_CURATE_JEV` → `scripts/curate_meajor.py` | CSV asli, label 1, kebijakan English/length | Audit JEV di `outputs/quality_jev_english_length_v3/`; pembanding kurasi opsional, tidak otomatis digabungkan dengan PPLX. |
| `scripts/compare_curations.py` | `--a` dan `--b`: dua audit cohort yang sama | CSV pada `--output`, berisi perbandingan keputusan kurasi. |
| `scripts/freeze_approved.py` | CSV sumber dan satu/lebih `--audit` | CSV pada `--output` serta `<output>.source.json`; mempertahankan semua baris yang diterima bersama, kecuali sampling diminta eksplisit. |
| `RUN_CURATE_LANGDETECT` | CSV asli | Diagnostik bahasa di `outputs/quality_langdetect_diagnostic_v2/`; bukan pengganti kebijakan PPLX English/length. |
| `RUN_PREPARE_PILOT` / `RUN_PREPARE_MAIN` → `scripts/prepare_meajor.py` | CSV asli | Cohort sampel seimbang dari protokol lama; tidak perlu dijalankan untuk pipeline seluruh label 1. |
| `scripts/evaluate_candidates.py` | Cohort, baseline satu victim dan CSV kandidat dengan prediksi yang sudah tersedia | `candidate_metrics.csv`, `summary.csv` jika ada metode; `paired_mcnemar.csv` jika tepat dua metode. |
| `scripts/evaluate_similarity.py` | Cohort dan kandidat yang disetujui | CSV pada `--output`: BLEU, ROUGE-L, Jaccard, retensi konten dan opsional SBERT. |

Untuk evaluasi kandidat, kolom yang diperlukan adalah `row_id`, `method`, `candidate_text`, `review_status`, dan `final_prediction` (`0`/`1`). `evaluate_candidates.py` memakai kandidat `approved` dengan teks dan prediksi valid, hanya untuk baris yang baseline victim deteksi sebagai positif. Gunakan kandidat/prediksi milik victim yang sama dengan baseline, dan direktori output terpisah per victim. Analisis similarity memakai semua kandidat approved yang memiliki teks dan ID dalam cohort, sehingga populasinya dapat berbeda dari evaluasi kandidat.

Script kandidat tidak memanggil victim untuk klasifikasi ulang dan tidak menghasilkan rewrite; input teks serta `final_prediction` harus sudah tersedia. Konfigurasi `attacker`, `gan` dan `methods` tidak menjalankan tahap tersebut secara otomatis. Contoh perintah analisis tersedia pada bagian **Reviewed offline candidates**.

Sebelum analisis similarity, pasang dependensi tambahan dengan `& $PipelinePython -m pip install -r requirements-analysis.txt`. Opsi `--sbert` memuat model embedding dan dapat memerlukan unduhan saat pertama dijalankan.

Jika memilih CSV frozen atau cohort alternatif, berikan path yang sama melalui `--input` pada baseline (tetap gunakan `--require-curated` untuk kebijakan aktif), dan `--dataset` pada semua script analisis. Gunakan direktori baseline terpisah agar hasil antar-cohort tidak bercampur.

### Keluaran akhir yang dibaca

```text
outputs/
  meajor_dataset_audit.json
  quality_pplx_english_length_v3/
    quality_audit.csv
    quality_accepted.csv
    quality_summary.json
    quality_manifest.json
    quality_checkpoint.jsonl
  curated_english_length_baseline/
    run_plan.csv
    <victim_id>_baseline.csv
    <victim_id>_baseline.csv.run.json
    <victim_id>_baseline.csv.checkpoint.jsonl
    metrics.csv
    <victim_id>_metadata.csv
```

Daftar ini adalah hasil yang akan dibuat oleh perintah di atas, bukan pernyataan bahwa inference sudah selesai. Pipeline utama selesai saat kurasi lengkap, semua baseline yang dipilih lengkap, lalu metrik dan laporan metadata berhasil dibuat untuk cohort yang sama. Tahap kandidat bersifat opsional. Untuk Linux/macOS, launcher `.sh` dengan nama yang sama tersedia; loop laporan di atas menggunakan PowerShell.

## Existing PPLX output is a different policy

`outputs/quality_pplx_label1` is retained as a historical readability-only run: 48,034 examined and 31,056 accepted. Its executed prompt did not enforce the current English and body-length requirements. Of those 31,056 accepted records, 12,998 have fewer than 100 body words under the existing word-count definition; records with exactly 100 words also fail the current rule. The old data remain available, but their acceptance flags alone do not prove eligibility. The new run screens all source label-1 rows, including old rejections, in a separate directory. No historical output is overwritten or relabeled.

## Curation controls and diagnostics

```powershell
python scripts/curate_meajor.py --input data/meajor_cleaned_preprocessed.csv --label 1 --provider ollama --model pplx-decider:latest --base-url http://127.0.0.1:11435 --policy english_length --min-words 101 --output-dir outputs/quality_pplx_english_length_v3
```

`--min-words` is inclusive and counts alphabetic tokens in the full body, excluding the subject; its default 101 implements **more than 100 words**. Short bodies are rejected locally before inference. PPLX judges English from up to 20,000 body characters. There is no langdetect score gate or separate readability/phishing gate in this policy. Record the truncation limitation in reports. Changing thresholds, instructions or policy requires a new output directory. Rerunning with unchanged settings resumes checkpoints, including deterministic precheck rejections.

Every selected input row remains in the audit. `quality_reason` distinguishes `body_too_short`, `english_requirement_failed` and `english_length_passed`. `language_screen`, `language_method`, `body_word_count`, `quality_min_words` and `model_text_truncated` make selection inspectable. Model confidence is retained for inspection but is not used as a language probability threshold. The accepted export contains only rows that pass both requirements.

`RUN_CURATE_JEV` applies the same policy using OpenRouter and needs an API key plus permission to send text to that provider. `RUN_CURATE_LANGDETECT` is explicitly a readability/language diagnostic in its own directory; it cannot establish phishing intent. The optional `RUN_PREPARE_PILOT` and `RUN_PREPARE_MAIN` scripts still create balanced samples and are not part of this label-1 pipeline.

For a separately chosen intersection of multiple audits, `freeze_approved.py --label 1` retains every commonly accepted row unless `--per-class` is explicitly provided. It preserves annotations from the first audit, which should be the primary English/length audit, and records all audit hashes in a sidecar.

## Metrics and reporting

```powershell
python scripts/baseline_metrics.py --dir outputs/curated_english_length_baseline --output outputs/curated_english_length_baseline/metrics.csv
python scripts/analyze_metadata.py --baseline outputs/curated_english_length_baseline/qwen35_9b_baseline.csv --output outputs/curated_english_length_baseline/metadata.csv
```

This is a positive-only evaluation. Report detection/recall, nonresponse coverage and uncertainty; single-class accuracy/precision/F1 do not establish representative two-class detector performance. Keep class support and failure denominators visible. Report duplicates and selection effects; the full label-1 source contains 1,192 duplicate excess texts. Curator/victim overlap requires independent review or sensitivity analysis.

## Reviewed offline candidates

The candidate/similarity scripts accept the same curated dataset schema and retain paired row IDs and hashes. They analyze pre-existing, human-reviewed candidate texts and recorded predictions. They do not implement an attacker, adaptive rewriting, or an optimization loop for bypassing detection. Raw prediction changes and text similarity do not by themselves establish preserved intent or validated success.

```powershell
python scripts/evaluate_candidates.py --baseline outputs/curated_english_length_baseline/qwen35_9b_baseline.csv --candidates path/to/reviewed_candidates.csv --output-dir outputs/offline_review
python scripts/evaluate_similarity.py --candidates path/to/reviewed_candidates.csv --output outputs/offline_review/similarity.csv --sbert
```

MeAJOR: [official release](https://zenodo.org/records/18471483), [dataset paper](https://doi.org/10.1016/j.dib.2026.112595). See `docs/RESEARCH_PROTOCOL.md` and `VALIDATION_STATUS.md` for the current scope and historical verification.
