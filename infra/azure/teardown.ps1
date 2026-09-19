<#
.SYNOPSIS
    Supprime toutes les ressources Azure du projet.

.DESCRIPTION
    Supprime le groupe de ressources entier, donc tout ce que deploy.ps1 a
    créé. Le réflexe à avoir sur un projet personnel : une infrastructure
    oubliée est une facture qui court.

    Le coffre Key Vault est purgé explicitement : par défaut Azure le
    conserve en suppression réversible pendant 90 jours, ce qui empêche de
    recréer un coffre du même nom.
#>

[CmdletBinding()]
param(
    [string] $ResourceGroup = "rg-vienna-vibe",
    [switch] $Force
)

$ErrorActionPreference = "Stop"

if (-not $Force) {
    $answer = Read-Host "Supprimer definitivement le groupe '$ResourceGroup' ? (oui/non)"
    if ($answer -ne "oui") { Write-Host "Annule."; exit 0 }
}

$vaults = az keyvault list -g $ResourceGroup --query "[].name" -o tsv
az group delete --name $ResourceGroup --yes --no-wait
Write-Host "Suppression du groupe lancee."

foreach ($vault in $vaults) {
    if ($vault) {
        Write-Host "Purge du coffre $vault (sinon son nom reste reserve 90 jours)."
        az keyvault purge --name $vault --no-wait 2>$null
    }
}
Write-Host "Termine."
