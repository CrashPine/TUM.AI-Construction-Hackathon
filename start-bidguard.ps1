param(
    [ValidateRange(1, 65535)][int]$Port = 8000,
    [ValidateRange(1, 65535)][int]$OllamaPort = 44445,
    [string]$Model = 'bonsai-2:27b',
    [ValidateRange(1, 100)][int]$Comparisons = 1,
    [ValidateRange(1, 3600)][int]$TimeoutSeconds = 240,
    [switch]$RulesOnly
)

$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    $options = @('--port', "$Port", '--max-requests', "$Comparisons", '--timeout', "$TimeoutSeconds")
    if (!$RulesOnly) {
        $ollama = "http://127.0.0.1:$OllamaPort"
        try {
            $models = (Invoke-RestMethod "$ollama/api/tags" -TimeoutSec 5).models.name
        } catch {
            throw "Ollama is not responding at $ollama. Start it, set -OllamaPort, or use -RulesOnly."
        }
        if ($Model -notin $models) {
            throw "Ollama at $ollama does not list $Model. Install it or pass -Model."
        }
        $options += @('--endpoint', "$ollama/api/chat", '--model', $Model)
    }
    uv sync --locked
    if ($LASTEXITCODE -ne 0) { throw 'Could not install locked dependencies with uv.' }
    uv run --locked python -m boqcheck.web @options
    if ($LASTEXITCODE -ne 0) { throw 'BidGuard did not start or exited with an error.' }
} finally {
    Pop-Location
}
