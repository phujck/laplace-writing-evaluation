<#
  FROZEN (2026-07-08, the shelving): the remote review surface is shelved. Do not
  run this to publish new bundles. SECURITY STANDING ITEM: the live bundle carries
  a broad gh token baked at build time - revoke it (and the three PATs pasted in
  the fifty-third transcript) in GitHub settings; any future publish bakes a
  fresh fine-grained PAT at run time, never a stored one.

  bake_and_publish_review.ps1 — the one-command "make it just work" for the remote
  review site. Bakes your working `gh` CLI token INTO the encrypted bundle (read
  internally, never printed), publishes to the phujck.github.io repo, commits, pushes.

  After this runs once, the live site pushes comments with ZERO token in the browser —
  you never touch a token screen again. The token rides inside the AES-encrypted blob
  (password-gated). You have accepted this trade (2026-07-04).

  Claude is hard-blocked from running this (a live credential crossing to a public
  destination), but you are not — it's your machine, your token, your repo.

  Usage:   .\scripts\bake_and_publish_review.ps1
  (edit the four vars below for a different paper)
#>
$ErrorActionPreference = "Stop"

$Root    = "synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.tex"
$Corpus  = "subset-sum-itqde"
$Slug    = "ssc"
$Password= "eigen"

$Laplace = Split-Path $PSScriptRoot -Parent
$Site    = Join-Path (Split-Path $Laplace -Parent) "phujck.github.io"
$Python  = Join-Path $Laplace ".venv\Scripts\python.exe"

Write-Host "== baking the gh token into the bundle and publishing ==" -ForegroundColor Cyan
& $Python (Join-Path $Laplace "scripts\export_review.py") $Root `
    --corpus $Corpus --slug $Slug --password $Password --use-gh-token `
    --publish (Join-Path $Site "review")
if ($LASTEXITCODE -ne 0) { throw "export failed" }

Write-Host "== committing + pushing the site ==" -ForegroundColor Cyan
Push-Location $Site
git add "review/$Slug"
git commit -m "Bake review token into the bundle (author's call)"
git push
Pop-Location

Write-Host ""
Write-Host "DONE. Live at https://gmccaul.co.uk/review/$Slug  (password: $Password)" -ForegroundColor Green
Write-Host "Give GitHub Pages a couple of minutes to rebuild, then comments push automatically." -ForegroundColor Green
