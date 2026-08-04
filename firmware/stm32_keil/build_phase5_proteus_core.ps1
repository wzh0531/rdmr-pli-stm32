$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildScript = Join-Path $projectRoot 'build_armcc.ps1'
$seed = [uint32]20260727

$scenarios = @(
    @{ Id = 501; Group = 'P1'; Algorithm = 'A0'; Trajectory = 'F1'; Amp = '0.50' },
    @{ Id = 502; Group = 'P1'; Algorithm = 'A1'; Trajectory = 'F1'; Amp = '0.50' },
    @{ Id = 503; Group = 'P1'; Algorithm = 'A2'; Trajectory = 'F1'; Amp = '0.50' },
    @{ Id = 504; Group = 'P1'; Algorithm = 'A3'; Trajectory = 'F1'; Amp = '0.50' },
    @{ Id = 505; Group = 'P2'; Algorithm = 'A2'; Trajectory = 'F2'; Amp = '0.20' },
    @{ Id = 506; Group = 'P2'; Algorithm = 'A3'; Trajectory = 'F2'; Amp = '0.20' },
    @{ Id = 507; Group = 'P2'; Algorithm = 'A2'; Trajectory = 'F2'; Amp = '0.50' },
    @{ Id = 508; Group = 'P2'; Algorithm = 'A3'; Trajectory = 'F2'; Amp = '0.50' },
    @{ Id = 509; Group = 'P2'; Algorithm = 'A2'; Trajectory = 'F2'; Amp = '1.00' },
    @{ Id = 510; Group = 'P2'; Algorithm = 'A3'; Trajectory = 'F2'; Amp = '1.00' },
    @{ Id = 511; Group = 'P3'; Algorithm = 'A2'; Trajectory = 'F3'; Amp = '0.50' },
    @{ Id = 512; Group = 'P3'; Algorithm = 'A3'; Trajectory = 'F3'; Amp = '0.50' }
)

foreach ($scenario in $scenarios) {
    $ampTag = $scenario.Amp.Replace('.', '')
    $stem = "PHASE5_{0}_S{1}_{2}_{3}_P{4}_Z20_REV14" -f `
        $scenario.Group, $scenario.Id, $scenario.Algorithm, `
        $scenario.Trajectory, $ampTag
    & powershell `
        -ExecutionPolicy Bypass `
        -File $buildScript `
        -Algorithm $scenario.Algorithm `
        -Trajectory $scenario.Trajectory `
        -Noise snr20 `
        -NearLine N0 `
        -PliAmplitude $scenario.Amp `
        -Seed $seed `
        -RunId 1 `
        -ScenarioId $scenario.Id `
        -EnableDwt 1 `
        -EmitDiagnostics 0 `
        -OutputStem $stem
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed for scenario $($scenario.Id)"
    }
}

Write-Output "Built $($scenarios.Count) Phase-5 Proteus core scenarios."
