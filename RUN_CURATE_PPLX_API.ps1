param(
    [string]$EndpointUrl = $env:PPLX_SYSTEMONE_URL,
    [string]$ModelId = $env:PPLX_MODEL_ID,
    [string]$OutputDirectory = 'outputs/quality_pplx_remote_english_length_v3',
    [string]$ResumePrechecksFrom = 'outputs/quality_pplx_english_length_v3',
    [int]$TimeoutSeconds = 180,
    [int]$RequestAttempts = 5
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$PipelinePython = if (Test-Path -LiteralPath '.venv/Scripts/python.exe') { '.venv/Scripts/python.exe' } else { 'python' }
if (-not $EndpointUrl) { $EndpointUrl = Read-Host 'Full direct HTTPS systemone URL (ask the server administrator)' }
if (-not $ModelId) { $ModelId = Read-Host 'Exact PPLX model ID accepted by that endpoint' }
$PromptedKey = -not $env:PPLX_API_KEY
try {
    if ($PromptedKey) {
        $SecureApiKey = Read-Host 'PPLX endpoint API key (hidden input)' -AsSecureString
        $KeyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureApiKey)
        try { $env:PPLX_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($KeyPointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($KeyPointer); $SecureApiKey.Dispose() }
    }
    # Test only the synthetic routing example before sending dataset records.
    & $PipelinePython scripts/check_decider.py --endpoint-url $EndpointUrl --model $ModelId --timeout $TimeoutSeconds --request-attempts $RequestAttempts
    if ($LASTEXITCODE -ne 0) { throw 'Decider connection/response test failed. Curation was not started.' }
    $CurationArguments = @(
        'scripts/curate_meajor.py', '--provider', 'decider', '--endpoint-url', $EndpointUrl,
        '--model', $ModelId, '--policy', 'english_length', '--min-words', '101', '--label', '1',
        '--input', 'data/meajor_cleaned_preprocessed.csv', '--output-dir', $OutputDirectory,
        '--timeout', "$TimeoutSeconds", '--request-attempts', "$RequestAttempts"
    )
    if ($ResumePrechecksFrom -and (Test-Path -LiteralPath "$ResumePrechecksFrom/quality_manifest.json") -and (Test-Path -LiteralPath "$ResumePrechecksFrom/quality_checkpoint.jsonl")) {
        $CurationArguments += @('--resume-prechecks-from', $ResumePrechecksFrom)
    }
    & $PipelinePython @CurationArguments
    if ($LASTEXITCODE -ne 0) { throw 'Curation stopped; rerun with unchanged arguments to resume saved checkpoints.' }
}
finally {
    if ($PromptedKey) { Remove-Item Env:PPLX_API_KEY -ErrorAction SilentlyContinue }
}
