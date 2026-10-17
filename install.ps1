# Install the rgs skills for Claude Code by linking them into ~/.claude/skills.
#
#   powershell -ExecutionPolicy Bypass -File install.ps1             # install (directory junctions)
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall  # remove the junctions
#
# Junctions keep the installed skills in sync with this repository: edit here, use everywhere.
# Existing folders that are not junctions to this repository are left alone.
# (ASCII only: Windows PowerShell 5.1 reads BOM-less scripts in the ANSI code page.)
param(
    [switch]$Uninstall,
    [string]$Target = (Join-Path $env:USERPROFILE '.claude\skills')
)

$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'skills'
$names = @('rgs-core', 'rgs-main', 'rgs-pr', 'rgs-facet')

function Get-LinkTarget([string]$path) {
    $item = Get-Item -LiteralPath $path -Force
    if ($item.LinkType -ne 'Junction' -and $item.LinkType -ne 'SymbolicLink') { return $null }
    return @($item.Target)[0]
}

if (-not (Test-Path -LiteralPath $Target)) {
    New-Item -ItemType Directory -Path $Target | Out-Null
}

foreach ($name in $names) {
    $link = Join-Path $Target $name
    $dest = Join-Path $source $name
    $exists = Test-Path -LiteralPath $link
    $current = if ($exists) { Get-LinkTarget $link } else { $null }

    if ($Uninstall) {
        if ($current) {
            # Removing a junction deletes only the link, never the repository folder.
            [System.IO.Directory]::Delete($link)
            Write-Host "removed  $link"
        } elseif ($exists) {
            Write-Warning "$link is a real folder, not a link; left in place"
        }
        continue
    }

    if ($current -and ((Resolve-Path -LiteralPath $current).Path -eq (Resolve-Path -LiteralPath $dest).Path)) {
        Write-Host "ok       $link -> $dest"
    } elseif ($exists) {
        Write-Warning "$link already exists and does not point to $dest; left in place"
    } else {
        New-Item -ItemType Junction -Path $link -Target $dest | Out-Null
        Write-Host "linked   $link -> $dest"
    }
}

if (-not $Uninstall) {
    $legacy = Join-Path $env:USERPROFILE '.claude\commands\rgs-facet.md'
    if (Test-Path -LiteralPath $legacy) {
        Write-Warning "$legacy exists and conflicts with /rgs-facet; please resolve manually (do not delete or edit automatically)"
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { Write-Warning 'python was not found on PATH; the rgs scripts need Python 3.10+' }
    $agy = Join-Path $env:LOCALAPPDATA 'agy\bin\agy.exe'
    if (-not (Test-Path -LiteralPath $agy) -and -not (Get-Command agy -ErrorAction SilentlyContinue)) {
        Write-Warning 'agy (Antigravity CLI) was not found; install it before using /rgs-main, /rgs-pr, or /rgs-facet'
    }
    Write-Host ''
    Write-Host 'Restart Claude Code (or open a new session) to load /rgs-main, /rgs-pr, and /rgs-facet.'
}
