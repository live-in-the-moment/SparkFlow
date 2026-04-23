<#
.SYNOPSIS
Runs sparkflow review-pipeline with safe PowerShell argument handling.

.DESCRIPTION
Wraps `python -X utf8 -m sparkflow review-pipeline` so Chinese paths,
spaces, and long argument lists do not break because of PowerShell
line-continuation or paste issues. You can either edit the preset
defaults inside this script and run it directly, or override any
setting with command-line parameters.

.EXAMPLE
.\scripts\run_review_pipeline.ps1

.EXAMPLE
.\scripts\run_review_pipeline.ps1 `
  -Path ".\docs\sample.dwg" `
  -ReviewDir ".\docs\评审意见" `
  -DwgBackend cli `
  -DwgConverter "D:\tools\ODAFileConverter.exe" `
  -WhatIf
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Position = 0)]
    [string]$Path = "",

    [string]$ReviewDir = "",

    [string]$Out = "",

    [string]$PythonExe = "",

    [ValidateSet("auto", "cli", "autocad")]
    [string]$DwgBackend = "",

    [string]$DwgConverter = "",

    [ValidateSet("ascii", "ezdxf", "auto")]
    [string]$DxfBackend = "",

    [string]$ProjectCode = "",

    [string]$Ruleset = "",

    [Nullable[double]]$DwgTimeout = $null,

    [double]$TopoTol = 0,

    [string]$Selection = "",

    [ValidateSet("electrical")]
    [string]$Graph = "",

    [switch]$SkipSparkFlowAudit,

    [string[]]$ExtraArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

# Edit these presets for your most common project.
$defaultDwg = "D:\code\project\moment\SparkFlow\docs\罗定供电局2025年中低压配电网第十批紧急项目--4项\罗定供电局2025年中低压配电网第十批紧急项目施工图--评审前\罗定供电局2025年中低压配电网第十批紧急项目施工图\附城所10kV朗溪线石龙台区改建工程\附件3 施工图\图纸-附城所10kV朗溪线石龙台区改建工程.dwg"
$defaultReview = "D:\code\project\moment\SparkFlow\docs\罗定供电局2025年中低压配电网第十批紧急项目--4项\评审意见及回复\评审技术要点"
$defaultOut = "tmp\review_pipeline_cli"
$defaultPythonExe = "python"
$defaultDwgBackend = "cli"
$defaultDwgConverter = "D:\code\project\qelectrotech\todxf\ODAFileConverter.exe"
$defaultDxfBackend = "ascii"
$defaultProjectCode = ""
$defaultRuleset = ""
$defaultDwgTimeout = $null
$defaultTopoTol = 1.0
$defaultSelection = "auto"
$defaultGraph = "electrical"
$defaultSkipSparkFlowAudit = $true

function Use-ConfiguredString {
    param(
        [Parameter(Mandatory)]
        [bool]$IsProvided,

        [AllowEmptyString()]
        [string]$CurrentValue,

        [AllowEmptyString()]
        [string]$DefaultValue
    )

    if ($IsProvided) {
        return $CurrentValue
    }

    return $DefaultValue
}

function Use-ConfiguredNumber {
    param(
        [Parameter(Mandatory)]
        [bool]$IsProvided,

        [Parameter(Mandatory)]
        [double]$CurrentValue,

        [Parameter(Mandatory)]
        [double]$DefaultValue
    )

    if ($IsProvided) {
        return $CurrentValue
    }

    return $DefaultValue
}

function Use-ConfiguredNullableNumber {
    param(
        [Parameter(Mandatory)]
        [bool]$IsProvided,

        [Nullable[double]]$CurrentValue,

        [Nullable[double]]$DefaultValue
    )

    if ($IsProvided) {
        return $CurrentValue
    }

    return $DefaultValue
}

$Path = Use-ConfiguredString -IsProvided $PSBoundParameters.ContainsKey("Path") -CurrentValue $Path -DefaultValue $defaultDwg
$ReviewDir = Use-ConfiguredString -IsProvided $PSBoundParameters.ContainsKey("ReviewDir") -CurrentValue $ReviewDir -DefaultValue $defaultReview
$Out = Use-ConfiguredString -IsProvided $PSBoundParameters.ContainsKey("Out") -CurrentValue $Out -DefaultValue $defaultOut
$PythonExe = Use-ConfiguredString -IsProvided $PSBoundParameters.ContainsKey("PythonExe") -CurrentValue $PythonExe -DefaultValue $defaultPythonExe
$DwgBackend = Use-ConfiguredString -IsProvided $PSBoundParameters.ContainsKey("DwgBackend") -CurrentValue $DwgBackend -DefaultValue $defaultDwgBackend
$DwgConverter = Use-ConfiguredString -IsProvided $PSBoundParameters.ContainsKey("DwgConverter") -CurrentValue $DwgConverter -DefaultValue $defaultDwgConverter
$DxfBackend = Use-ConfiguredString -IsProvided $PSBoundParameters.ContainsKey("DxfBackend") -CurrentValue $DxfBackend -DefaultValue $defaultDxfBackend
$ProjectCode = Use-ConfiguredString -IsProvided $PSBoundParameters.ContainsKey("ProjectCode") -CurrentValue $ProjectCode -DefaultValue $defaultProjectCode
$Ruleset = Use-ConfiguredString -IsProvided $PSBoundParameters.ContainsKey("Ruleset") -CurrentValue $Ruleset -DefaultValue $defaultRuleset
$DwgTimeout = Use-ConfiguredNullableNumber -IsProvided $PSBoundParameters.ContainsKey("DwgTimeout") -CurrentValue $DwgTimeout -DefaultValue $defaultDwgTimeout
$TopoTol = Use-ConfiguredNumber -IsProvided $PSBoundParameters.ContainsKey("TopoTol") -CurrentValue $TopoTol -DefaultValue $defaultTopoTol
$Selection = Use-ConfiguredString -IsProvided $PSBoundParameters.ContainsKey("Selection") -CurrentValue $Selection -DefaultValue $defaultSelection
$Graph = Use-ConfiguredString -IsProvided $PSBoundParameters.ContainsKey("Graph") -CurrentValue $Graph -DefaultValue $defaultGraph
$skipSparkFlowAuditEnabled = if ($PSBoundParameters.ContainsKey("SkipSparkFlowAudit")) {
    $SkipSparkFlowAudit.IsPresent
} else {
    $defaultSkipSparkFlowAudit
}

if ([string]::IsNullOrWhiteSpace($Path)) {
    throw "DWG/DXF path is empty. Edit `$defaultDwg in scripts\\run_review_pipeline.ps1 or pass -Path."
}

if ([string]::IsNullOrWhiteSpace($ReviewDir)) {
    throw "Review directory is empty. Edit `$defaultReview in scripts\\run_review_pipeline.ps1 or pass -ReviewDir."
}

function Resolve-InputPath {
    param(
        [Parameter(Mandatory)]
        [string]$Candidate,

        [Parameter(Mandatory)]
        [string]$Label
    )

    if (Test-Path -LiteralPath $Candidate) {
        return (Resolve-Path -LiteralPath $Candidate).Path
    }

    $repoRelative = Join-Path $repoRoot $Candidate
    if (Test-Path -LiteralPath $repoRelative) {
        return (Resolve-Path -LiteralPath $repoRelative).Path
    }

    throw "$Label not found: $Candidate"
}

function Resolve-OutputPath {
    param(
        [Parameter(Mandatory)]
        [string]$Candidate
    )

    if ([System.IO.Path]::IsPathRooted($Candidate)) {
        return $Candidate
    }

    return (Join-Path $repoRoot $Candidate)
}

function Add-StringArgument {
    param(
        [Parameter(Mandatory)]
        [System.Collections.Generic.List[string]]$Args,

        [Parameter(Mandatory)]
        [string]$Name,

        [AllowEmptyString()]
        [string]$Value
    )

    if (-not [string]::IsNullOrWhiteSpace($Value)) {
        $Args.Add($Name)
        $Args.Add($Value)
    }
}

function Format-Argument {
    param(
        [Parameter(Mandatory)]
        [string]$Value
    )

    if ($Value -match '[\s"]') {
        return '"' + $Value.Replace('"', '\"') + '"'
    }

    return $Value
}

if ($DwgBackend -eq "cli" -and [string]::IsNullOrWhiteSpace($DwgConverter)) {
    throw "When -DwgBackend cli is used, -DwgConverter is required."
}

$drawingPath = Resolve-InputPath -Candidate $Path -Label "DWG/DXF path"
$reviewPath = Resolve-InputPath -Candidate $ReviewDir -Label "Review directory"
$outputPath = Resolve-OutputPath -Candidate $Out

$pythonArgs = [System.Collections.Generic.List[string]]::new()
$pythonArgs.Add("-X")
$pythonArgs.Add("utf8")
$pythonArgs.Add("-m")
$pythonArgs.Add("sparkflow")
$pythonArgs.Add("review-pipeline")
$pythonArgs.Add($drawingPath)
$pythonArgs.Add("--review-dir")
$pythonArgs.Add($reviewPath)
$pythonArgs.Add("--out")
$pythonArgs.Add($outputPath)
Add-StringArgument -Args $pythonArgs -Name "--project-code" -Value $ProjectCode
Add-StringArgument -Args $pythonArgs -Name "--ruleset" -Value $Ruleset
$pythonArgs.Add("--dxf-backend")
$pythonArgs.Add($DxfBackend)
$pythonArgs.Add("--dwg-backend")
$pythonArgs.Add($DwgBackend)
Add-StringArgument -Args $pythonArgs -Name "--dwg-converter" -Value $DwgConverter
if ($null -ne $DwgTimeout) {
    $pythonArgs.Add("--dwg-timeout")
    $pythonArgs.Add($DwgTimeout.Value.ToString([System.Globalization.CultureInfo]::InvariantCulture))
}
$pythonArgs.Add("--topo-tol")
$pythonArgs.Add($TopoTol.ToString([System.Globalization.CultureInfo]::InvariantCulture))
$pythonArgs.Add("--selection")
$pythonArgs.Add($Selection)
$pythonArgs.Add("--graph")
$pythonArgs.Add($Graph)
if ($skipSparkFlowAuditEnabled) {
    $pythonArgs.Add("--skip-sparkflow-audit")
}
foreach ($arg in $ExtraArgs) {
    $pythonArgs.Add($arg)
}

$displayCommand = @($PythonExe) + @($pythonArgs)
$displayCommandText = ($displayCommand | ForEach-Object { Format-Argument -Value $_ }) -join " "

Write-Host "RepoRoot : $repoRoot"
Write-Host "Command  : $displayCommandText"

Push-Location $repoRoot
try {
    if ($PSCmdlet.ShouldProcess($drawingPath, "Run sparkflow review-pipeline")) {
        $outParent = Split-Path -Parent $outputPath
        if (-not [string]::IsNullOrWhiteSpace($outParent) -and -not (Test-Path -LiteralPath $outParent)) {
            New-Item -ItemType Directory -Path $outParent -Force | Out-Null
        }

        & $PythonExe @pythonArgs
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
}
finally {
    Pop-Location
}
