param(
    [string]$BaseUrl = 'https://llms.si-lab.org',
    [string]$ChatModel = 'openai/gpt-oss-120b',
    [string]$ToolId = 'server:pplxdeciderflash',
    [string]$OutputDirectory = 'outputs/quality_pplx_openwebui_english_length_v3',
    [string]$ResumeFrom = 'outputs/quality_pplx_english_length_v3',
    [int]$TimeoutSeconds = 300,
    [int]$RequestAttempts = 5,
    [switch]$PromptApiKey
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$PipelinePython = if (Test-Path -LiteralPath '.venv/Scripts/python.exe') { '.venv/Scripts/python.exe' } else { 'python' }
$PreviousApiKey = $env:OPENWEBUI_API_KEY
$PromptedKey = $PromptApiKey -or (-not $env:OPENWEBUI_API_KEY)
try {
    if ($PromptedKey) {
        Write-Host 'Enter only the Open WebUI account API key, without Bearer or quotation marks.'
        $SecureApiKey = Read-Host 'Open WebUI API key for llms.si-lab.org (hidden input)' -AsSecureString
        $KeyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureApiKey)
        try { $env:OPENWEBUI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($KeyPointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($KeyPointer); $SecureApiKey.Dispose() }
    } else { Write-Host 'Using OPENWEBUI_API_KEY from environment. Use -PromptApiKey to enter a different key.' }
    & $PipelinePython scripts/check_decider.py --transport openwebui --webui-url $BaseUrl --chat-model $ChatModel --tool-id $ToolId --timeout $TimeoutSeconds --request-attempts $RequestAttempts --response-output outputs/openwebui_decider_connection_test.json
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'PPLX verification failed; curation was not started and checkpoints are unchanged.' -ForegroundColor Red
        Write-Host 'For HTTP 401/403, verify your Open WebUI key/account access, then rerun with -PromptApiKey. A saved response file may be from an earlier attempt.'
        exit 1
    }
    $CurationArguments = @(
        'scripts/curate_meajor.py', '--provider', 'openwebui', '--webui-url', $BaseUrl,
        '--chat-model', $ChatModel, '--tool-id', $ToolId,
        '--policy', 'english_length', '--min-words', '101', '--label', '1',
        '--input', 'data/meajor_cleaned_preprocessed.csv', '--output-dir', $OutputDirectory,
        '--timeout', "$TimeoutSeconds", '--request-attempts', "$RequestAttempts"
    )
    if ($ResumeFrom -and (Test-Path -LiteralPath "$ResumeFrom/quality_manifest.json") -and (Test-Path -LiteralPath "$ResumeFrom/quality_checkpoint.jsonl")) {
        # User confirmed these routes point to the same PPLX backend; record this in the manifest.
        $CurationArguments += @('--resume-from', $ResumeFrom, '--same-decider-backend')
    }
    & $PipelinePython @CurationArguments
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Curation stopped; checkpoint preserved. See $OutputDirectory/quality_last_error.json and rerun with unchanged settings." -ForegroundColor Red
        exit 1
    }
}
finally {
    if ($PromptedKey) {
        if ($PreviousApiKey) { $env:OPENWEBUI_API_KEY = $PreviousApiKey }
        else { Remove-Item Env:OPENWEBUI_API_KEY -ErrorAction SilentlyContinue }
    }
}
