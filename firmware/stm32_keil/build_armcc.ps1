param(
    [ValidateSet('A0', 'A1', 'A2', 'A3', 'B1', 'B2', 'B3', 'B4')]
    [string]$Algorithm = 'A3',
    [ValidateSet('F0', 'F1', 'F2', 'F3', 'F4', 'F5')]
    [string]$Trajectory = 'F1',
    [ValidateSet('none', 'snr20', 'snr10')]
    [string]$Noise = 'none',
    [ValidateSet('N0', 'N1', 'N2', 'N3')]
    [string]$NearLine = 'N0',
    [ValidateSet('0.20', '0.50', '1.00')]
    [string]$PliAmplitude = '0.50',
    [uint32]$Seed = 0,
    [uint32]$RunId = 1,
    [uint32]$ScenarioId = 101,
    [ValidateSet(0, 1)]
    [int]$EnableDwt = 1,
    [ValidateSet(0, 1)]
    [int]$EmitDiagnostics = 0,
    [ValidateSet(0, 1)]
    [int]$ProteusBuild = 1,
    [ValidateSet(0, 1)]
    [int]$TrackerSearchMode = 1,
    [ValidateRange(1, 999)]
    [uint32]$FirmwareRevision = 14,
    [string]$OutputStem = '',
    [string]$CubePackageRoot = $env:STM32CUBE_F1_ROOT,
    [string]$ArmccBinRoot = $env:ARMCC_BIN
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Resolve-Path (Join-Path $projectRoot '..\..')
if ([string]::IsNullOrWhiteSpace($CubePackageRoot)) {
    throw 'Set STM32CUBE_F1_ROOT or pass -CubePackageRoot with the STM32CubeF1 package path.'
}
if ([string]::IsNullOrWhiteSpace($ArmccBinRoot)) {
    throw 'Set ARMCC_BIN or pass -ArmccBinRoot with the ARMCC bin directory.'
}
$CubePackageRoot = (Resolve-Path -LiteralPath $CubePackageRoot).Path
$ArmccBinRoot = (Resolve-Path -LiteralPath $ArmccBinRoot).Path
$buildRoot = Join-Path $projectRoot 'build'
$objectRoot = Join-Path $buildRoot ("obj_{0}_{1}_{2}_s{3}_dwt{4}_diag{5}_prot{6}_search{7}_rev{8}" -f $Algorithm, $Trajectory, $Noise, $Seed, $EnableDwt, $EmitDiagnostics, $ProteusBuild, $TrackerSearchMode, $FirmwareRevision)

$algorithmIds = @{ A0 = 0; A1 = 1; A2 = 2; A3 = 3; B1 = 4; B2 = 5; B3 = 6; B4 = 7 }
$trajectoryIds = @{ F0 = 0; F1 = 1; F2 = 2; F3 = 3; F4 = 4; F5 = 5 }
$noiseIds = @{ none = 0; snr20 = 1; snr10 = 2 }
$nearLineIds = @{ N0 = 0; N1 = 1; N2 = 2; N3 = 3 }

if ([string]::IsNullOrWhiteSpace($OutputStem)) {
    $OutputStem = "rdmr_stm32_{0}_{1}_{2}_s{3}_search{4}_rev{5}" -f $Algorithm, $Trajectory, $Noise, $Seed, $TrackerSearchMode, $FirmwareRevision
}
if ($OutputStem -notmatch '^[A-Za-z0-9_-]+$') {
    throw 'OutputStem may contain only letters, digits, underscore, and hyphen'
}

New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
New-Item -ItemType Directory -Force -Path $objectRoot | Out-Null

$deviceInclude = Join-Path $CubePackageRoot 'Drivers\CMSIS\Device\ST\STM32F1xx\Include'
$cmsisInclude = Join-Path $CubePackageRoot 'Drivers\CMSIS\Include'
$coreInclude = Join-Path $repositoryRoot 'firmware\core'

$common = @(
    '--cpu', 'Cortex-M3',
    '--c99',
    '-g',
    '-O2',
    '--split_sections',
    '-DSTM32F103xB',
    ("-DRDMR_DEMO_ALGORITHM={0}" -f $algorithmIds[$Algorithm]),
    ("-DRDMR_DEMO_TRAJECTORY={0}" -f $trajectoryIds[$Trajectory]),
    ("-DRDMR_DEMO_NOISE={0}" -f $noiseIds[$Noise]),
    ("-DRDMR_DEMO_NEAR_LINE={0}" -f $nearLineIds[$NearLine]),
    ("-DRDMR_DEMO_PLI_AMPLITUDE={0}f" -f $PliAmplitude),
    ("-DRDMR_DEMO_SEED={0}U" -f $Seed),
    ("-DRDMR_DEMO_RUN_ID={0}U" -f $RunId),
    ("-DRDMR_DEMO_SCENARIO_ID={0}U" -f $ScenarioId),
    ("-DRDMR_ENABLE_DWT={0}" -f $EnableDwt),
    ("-DRDMR_EMIT_INIT_DIAGNOSTICS={0}" -f $EmitDiagnostics),
    ("-DRDMR_PROTEUS_BUILD={0}" -f $ProteusBuild),
    ("-DRDMR_TRACKER_SEARCH_MODE={0}" -f $TrackerSearchMode),
    ("-DRDMR_FIRMWARE_REVISION={0}" -f $FirmwareRevision),
    '-I', $deviceInclude,
    '-I', $cmsisInclude,
    '-I', $coreInclude
)

$sources = @(
    (Join-Path $projectRoot 'App\main.c'),
    (Join-Path $projectRoot 'App\system_stm32f1xx.c'),
    (Join-Path $repositoryRoot 'firmware\core\rdmr_algorithm.c'),
    (Join-Path $repositoryRoot 'firmware\core\rdmr_cycle_stats.c'),
    (Join-Path $repositoryRoot 'firmware\core\rdmr_pli.c'),
    (Join-Path $repositoryRoot 'firmware\core\rdmr_signal_protocol.c'),
    (Join-Path $repositoryRoot 'firmware\core\rdmr_trig.c')
)

$objects = @()
foreach ($source in $sources) {
    $objectName = [System.IO.Path]::GetFileNameWithoutExtension($source) + '.o'
    $object = Join-Path $objectRoot $objectName
    & (Join-Path $ArmccBinRoot 'armcc.exe') @common -c $source -o $object
    if ($LASTEXITCODE -ne 0) {
        throw "armcc failed for $source"
    }
    $objects += $object
}

$startupObject = Join-Path $objectRoot 'startup_stm32f103xb.o'
& (Join-Path $ArmccBinRoot 'armasm.exe') `
    --cpu Cortex-M3 `
    -g `
    (Join-Path $projectRoot 'Startup\startup_stm32f103xb.s') `
    -o $startupObject
if ($LASTEXITCODE -ne 0) {
    throw 'armasm failed'
}
$objects += $startupObject

$elf = Join-Path $buildRoot ($OutputStem + '.axf')
$map = Join-Path $buildRoot ($OutputStem + '.map')
& (Join-Path $ArmccBinRoot 'armlink.exe') `
    --cpu Cortex-M3 `
    --scatter (Join-Path $projectRoot 'rdmr_stm32.sct') `
    --map `
    --list $map `
    --entry Reset_Handler `
    --info sizes,totals `
    $objects `
    -o $elf
if ($LASTEXITCODE -ne 0) {
    throw 'armlink failed'
}

$hex = Join-Path $buildRoot ($OutputStem + '.hex')
& (Join-Path $ArmccBinRoot 'fromelf.exe') --i32combined --output $hex $elf
if ($LASTEXITCODE -ne 0) {
    throw 'fromelf failed'
}

Write-Output "ALGORITHM: $Algorithm"
Write-Output "TRAJECTORY: $Trajectory"
Write-Output "NOISE: $Noise"
Write-Output "NEAR_LINE: $NearLine"
Write-Output "PLI_AMPLITUDE: $PliAmplitude"
Write-Output "SEED: $Seed"
Write-Output "RUN_ID: $RunId"
Write-Output "SCENARIO_ID: $ScenarioId"
Write-Output "DWT: $EnableDwt"
Write-Output "DIAGNOSTICS: $EmitDiagnostics"
Write-Output "PROTEUS_BUILD: $ProteusBuild"
Write-Output "TRACKER_SEARCH_MODE: $TrackerSearchMode"
Write-Output "FIRMWARE_REVISION: $FirmwareRevision"
Write-Output "ELF: $elf"
Write-Output "HEX: $hex"
Write-Output "MAP: $map"
