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

Terminal menampilkan persentase selesai, jumlah baris dari checkpoint, waktu sesi berjalan, sisa pekerjaan lokal/model, **ETA**, dan perkiraan tanggal/jam selesai anotasi dalam zona waktu komputer (offset UTC ikut ditampilkan). ETA memakai rata-rata hingga 50 durasi terbaru untuk setiap jenis pekerjaan; baris checkpoint tidak dipakai sebagai sampel kecepatan. Sebelum sampel waktu yang dibutuhkan tersedia, statusnya `collecting timing samples`. Estimasi belum mencakup ekspor CSV akhir dan dapat berubah mengikuti kecepatan model/retry. Progres diperbarui setelah baris selesai: pada sampel pertama tiap jenis, setiap 100 baris baru, atau setelah interval 30 detik. Interval bisa diubah melalui `--progress-every` pada perintah Python; saat satu permintaan model masih menunggu, tampilan belum diperbarui. Sesudah ekspor, waktu selesai aktual dicetak. Perubahan tampilan ini tetap kompatibel dengan checkpoint kebijakan yang sama.

`english_score` memang kosong pada kebijakan `english_length`: field itu digunakan oleh diagnostik langdetect. Jika body kurang dari 101 kata, baris ditolak lokal dengan `language_screen=not_evaluated`, `language_method=not_checked_length`, dan confidence kosong karena PPLX belum dipanggil. Jika PPLX dipanggil, keputusannya tersimpan di `language_screen` dan confidence pilihan model di `quality_confidence` jika API menyediakannya. Confidence tersebut bukan skor bahasa dari langdetect; ketika pilihannya `not_usable`, confidence mengacu pada pilihan penolakan itu.

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

## Melanjutkan kurasi lewat Open WebUI dosen (jalur yang dipilih)

Launcher ini mengikuti `openwebui_api_test (1).py` yang diberikan pengguna:

| Pengaturan | Nilai |
| --- | --- |
| URL | `https://llms.si-lab.org/api/chat/completions` |
| Model pemanggil tool di SGLang | `openai/gpt-oss-120b` |
| Tool penentu keputusan | `server:pplxdeciderflash`, operasi server `classify_with_pplx_decider` (format `systemone` langsung juga didukung) |
| Mode Open WebUI | `params.function_calling=legacy`, `stream=false` |
| Kredensial | API key akun Open WebUI; environment `OPENWEBUI_API_KEY` atau prompt tersembunyi |
| Checkpoint sumber | `outputs/quality_pplx_english_length_v3/` |
| Keluaran lanjutan | `outputs/quality_pplx_openwebui_english_length_v3/` |

**Hentikan proses kurasi lama sebelum berpindah jalur**, lalu jalankan dari PowerShell di folder project:

```powershell
.\RUN_CURATE_PPLX_OPENWEBUI.ps1
```

API key diminta melalui input tersembunyi; jangan taruh key di chat atau source. Jika `OPENWEBUI_API_KEY` sudah tersedia di environment, launcher menggunakannya. Key yang dimasukkan melalui prompt dibersihkan dari environment launcher setelah proses selesai. Default timeout adalah 300 detik per percobaan dengan maksimum 5 percobaan untuk gangguan sementara. HTTP 401/403 langsung dihentikan agar izin/key dapat diperbaiki.

Alur launcher:

1. `scripts/check_decider.py --transport openwebui` mengirim contoh HTTP 401 dari pengguna. GPT-OSS diminta memanggil `systemone`, bukan memilih departemen sendiri. Respons uji sintetis disimpan di `outputs/openwebui_decider_connection_test.json` jika server memberikan respons JSON.
2. Adapter mengambil hasil dari `sources` yang ditandai sebagai hasil tool PPLX. Respons server yang sudah diamati memakai `server:pplxdeciderflash/classify_with_pplx_decider`, dengan argumen datar `state`, `instructions`, `criteria` dan jawaban `answers.decision`. Script memverifikasi ketiga argumen tersebut sama persis dengan permintaan, kemudian memetakan kunci `decision` ke `department` pada uji atau `quality` pada kurasi; nilai pilihan, probability dan confidence tidak diubah. Format operasi `systemone` dengan `state/questions` juga didukung. Teks jawaban GPT-OSS, tool call yang belum dieksekusi, argumen yang diubah, hasil error, atau hasil tanpa bukti tool tidak diterima. Jika pemeriksaan gagal, dataset belum dikirim dan tidak ada pilihan departemen yang ditebak.
3. Jika uji berhasil, kurasi membaca hanya label 1. Body <101 kata ditolak lokal. Untuk body yang cukup panjang, GPT-OSS hanya meneruskan tugas bahasa Inggris ke PPLX. Keputusan disimpan dari hasil PPLX, beserta identitas pemanggil tool dan hash argumen/hasil tool.
4. **Pengguna mengonfirmasi kedua jalur menggunakan backend PPLX yang sama.** Atas dasar itu, launcher memakai `--resume-from ... --same-decider-backend` untuk mempertahankan keputusan lama. Manifest mencatat konfirmasi operator, endpoint/model sebelumnya dan hash snapshot checkpoint; ini bukan verifikasi independen kesamaan bobot model. Label provider/model pada keputusan lama tetap dipertahankan, bukan diubah menjadi panggilan Open WebUI.
5. Snapshot tetap dari checkpoint lama dibuat pada pemakaian pertama di `imported_checkpoint.snapshot.jsonl`. Hanya baris yang belum selesai yang diproses. Rerun launcher yang sama melanjutkan checkpoint pada folder Open WebUI. Jangan hapus snapshot atau manifest yang diperlukan untuk resume.

Dokumentasi [Open WebUI: server-side tool calling](https://docs.openwebui.com/reference/server-side-tool-calling/#path-b-one-request-answer-in-the-body) menjelaskan respons mode legacy dengan field `sources`. Versi server tetap perlu diuji; jika struktur metadata berbeda atau bukti tool tidak dikembalikan, script berhenti dengan pesan yang jelas. Jangan menafsirkan jawaban chat sebagai pengganti hasil Decider. Jika terjadi error HTTP sebelum respons diterima, file respons uji mungkin tidak ada atau masih berasal dari uji sebelumnya; gunakan status exit/error percobaan terbaru.

Contoh mengganti waktu tunggu, atau menguji koneksi saja jika environment key sudah diisi:

```powershell
.\RUN_CURATE_PPLX_OPENWEBUI.ps1 -TimeoutSeconds 600 -RequestAttempts 5
python scripts/check_decider.py --transport openwebui --response-output outputs/openwebui_decider_connection_test.json
```

Untuk memakai hasil lanjutan pada baseline, gunakan path eksplisit agar tidak kembali membaca folder lokal:

```powershell
$PipelinePython = if (Test-Path '.venv/Scripts/python.exe') { '.venv/Scripts/python.exe' } else { 'python' }
$WebUIDataset = 'outputs/quality_pplx_openwebui_english_length_v3/quality_accepted.csv'
$WebUIBaseline = 'outputs/curated_openwebui_english_length_baseline'
& $PipelinePython scripts/run_baseline.py --input $WebUIDataset --require-curated --label 1 --output-dir $WebUIBaseline --dry-run
& $PipelinePython scripts/run_baseline.py --input $WebUIDataset --require-curated --label 1 --output-dir $WebUIBaseline
& $PipelinePython scripts/baseline_metrics.py --dataset $WebUIDataset --dir $WebUIBaseline --output "$WebUIBaseline/metrics.csv"
```

Baseline victim masih memakai endpoint yang dikonfigurasi di pipeline baseline; perubahan ini memindahkan koneksi **kurasi**. Gunakan `--dataset $WebUIDataset` pada laporan metadata dan analisis kandidat yang memakai cohort ini. Jika ternyata backend lama berbeda, jangan gunakan konfirmasi kesamaan: jalankan script Python dengan `--resume-prechecks-from` untuk memakai kembali penolakan panjang saja, dalam output directory baru.

## Alternatif: endpoint PPLX langsung dengan API key

File contoh `openwebui_api_test (1).py` memakai `https://llms.si-lab.org/api/chat/completions`, model GPT-OSS dan `tool_ids=["server:pplxdeciderflash"]`. Itu adalah permintaan chat dengan tool yang diaktifkan, bukan URL langsung Decider. Keberadaan tool ID tidak membuktikan bahwa `/v1/systemone` tersedia pada host Open WebUI yang sama. [Dokumentasi Open WebUI](https://docs.openwebui.com/reference/api-endpoints/) membedakan pemanggilan chat dengan tool server; route dan izin pada instalasi server tetap perlu dikonfirmasi.

Provider alternatif `decider` menggunakan **respons terstruktur `systemone` langsung**, tanpa GPT-OSS sebagai pemanggil tool. Ini memerlukan informasi tambahan dan bukan launcher Open WebUI di atas. Siapkan dari administrator server:

- URL lengkap HTTPS endpoint yang berakhir `/systemone` (termasuk prefix seperti `/v1` jika diperlukan).
- ID model yang benar untuk payload API PPLX Decider Flash v1.2; nama tampilan atau tag model lokal belum tentu sama dengan ID server.
- Bearer API key yang memang diberi akses ke endpoint tersebut. Key akun Open WebUI tidak otomatis berlaku pada backend PPLX terpisah.

Jalankan dari PowerShell:

```powershell
.\RUN_CURATE_PPLX_API.ps1
```

Launcher menanyakan URL, ID model, dan API key dengan input key tersembunyi. Key tidak disimpan dalam source, manifest atau argumen command line; key yang dimasukkan melalui prompt dibersihkan dari environment launcher setelah selesai. Jika ingin menyiapkan sendiri, launcher juga membaca `PPLX_SYSTEMONE_URL`, `PPLX_MODEL_ID` dan `PPLX_API_KEY` dari environment. Jangan menempelkan key di README atau chat. Endpoint HTTPS dipakai sebagaimana diberikan, tanpa mengikuti redirect yang dapat meneruskan kredensial ke lokasi lain.

Urutan launcher API:

1. `scripts/check_decider.py` mengirim contoh pelanggan mendapat HTTP 401 setelah rotasi credential ke `systemone`. Opsi technical/billing/sales dikirim sebagai criteria. Script melaporkan pilihan Decider, probability jika tersedia, dan confidence secara terpisah; tidak menentukan departemen sendiri. Respons chat, jawaban tidak valid, atau error autentikasi menghentikan launcher sebelum dataset dikirim.
2. `scripts/curate_meajor.py --provider decider --label 1 --policy english_length --min-words 101` memproses cohort label 1. Policy ini menolak override `--label 0` atau `--label all`.
3. Secara default, penolakan panjang teks dari `outputs/quality_pplx_english_length_v3` diimpor jika manifest dan checkpoint tersedia. `--resume-prechecks-from` memverifikasi kesamaan sumber dan aturan, mengecek hash baris, dan menghitung ulang keputusan panjang secara lokal. File lama tidak diubah. **Keputusan model lama tidak diimpor** karena endpoint/model berbeda; baris tersebut dinilai ulang oleh model server. Ini melanjutkan pekerjaan yang dapat digunakan kembali, bukan menyatakan dua model identik.
4. Hasil baru tersimpan di `outputs/quality_pplx_remote_english_length_v3/`. Rerun launcher dengan URL, model, sumber, folder impor dan output yang sama akan melanjutkan seluruh keputusan remote yang sudah tersimpan. Tidak perlu mengulang baris yang sudah selesai pada endpoint remote tersebut.

Launcher memakai maksimum 5 percobaan per baris, dengan backoff 1, 2, 4, 8 detik dan timeout 180 detik per percobaan. Connection reset, timeout dan HTTP sementara seperti 429/502/503/504 di-retry. HTTP 401/403 tidak di-retry; periksa key/izin. Percobaan ulang setelah timeout dapat mengulang pekerjaan di server meskipun hasil belum diterima client. Setelah retry habis, proses berhenti dan mempertahankan checkpoint; tidak mencatat error sebagai penolakan bahasa. Untuk launcher lokal, retry yang sama tersedia dengan default 3 percobaan.

Contoh mengatur waktu tunggu tanpa mengubah aturan kurasi:

```powershell
.\RUN_CURATE_PPLX_API.ps1 -TimeoutSeconds 300 -RequestAttempts 5
```

Untuk menguji hanya koneksi setelah environment diisi, tanpa menjalankan kurasi:

```powershell
python scripts/check_decider.py
```

Jika URL `systemone` tidak dapat diakses langsung dan server hanya menyediakan tool melalui Open WebUI, minta route proxy yang disetujui administrator atau schema tool/API yang terpasang. Jangan menebak route ataupun menggunakan teks jawaban GPT-OSS sebagai hasil PPLX. Integrasi langsung belum terverifikasi pada server pengguna sampai URL, model, key dan schema respons berhasil diuji.

Sesudah kurasi API lengkap, pilih **dataset remote yang sama** untuk baseline dan seluruh analisis. Launcher baseline lama tetap mengarah ke hasil lokal, sehingga gunakan perintah eksplisit berikut (victim tetap memakai endpoint pada konfigurasi baseline saat ini):

```powershell
$PipelinePython = if (Test-Path '.venv/Scripts/python.exe') { '.venv/Scripts/python.exe' } else { 'python' }
$RemoteDataset = 'outputs/quality_pplx_remote_english_length_v3/quality_accepted.csv'
$RemoteBaseline = 'outputs/curated_remote_english_length_baseline'
& $PipelinePython scripts/run_baseline.py --input $RemoteDataset --require-curated --label 1 --output-dir $RemoteBaseline --dry-run
& $PipelinePython scripts/run_baseline.py --input $RemoteDataset --require-curated --label 1 --output-dir $RemoteBaseline
& $PipelinePython scripts/baseline_metrics.py --dataset $RemoteDataset --dir $RemoteBaseline --output "$RemoteBaseline/metrics.csv"
```

Gunakan juga `--dataset $RemoteDataset` pada `analyze_metadata.py`, `evaluate_candidates.py` dan `evaluate_similarity.py` jika menganalisis cohort remote.

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
