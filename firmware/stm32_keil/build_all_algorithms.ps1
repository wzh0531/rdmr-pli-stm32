$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildScript = Join-Path $projectRoot 'build_armcc.ps1'

foreach ($algorithm in @('A0', 'A1', 'A2', 'A3')) {
    & powershell `
        -ExecutionPolicy Bypass `
        -File $buildScript `
        -Algorithm $algorithm `
        -Trajectory F1 `
        -Noise none `
        -Seed 0 `
        -OutputStem ("rdmr_stm32_{0}_F1_none_s0" -f $algorithm)
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed for $algorithm"
    }
}
