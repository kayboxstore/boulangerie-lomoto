$nodeDir = "C:\Program Files\nodejs"
$npmGlobalDir = Join-Path $env:APPDATA "npm"

foreach ($pathToAdd in @($nodeDir, $npmGlobalDir)) {
    if ((Test-Path $pathToAdd) -and (($env:Path -split ';') -notcontains $pathToAdd)) {
        $env:Path = "$pathToAdd;$env:Path"
    }
}

function Resolve-Tool {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Candidates
    )

    foreach ($candidate in $Candidates) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) {
            return $command.Source
        }
    }

    throw "Outil introuvable : $($Candidates -join ', ')"
}

function Invoke-Tool {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Candidates,

        [string[]]$Arguments = @()
    )

    $tool = Resolve-Tool -Candidates $Candidates
    & $tool @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "La commande a echoue ($LASTEXITCODE) : $tool $($Arguments -join ' ')"
    }
}
