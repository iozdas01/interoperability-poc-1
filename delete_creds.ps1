$creds = cmdkey /list
foreach ($line in $creds) {
    if ($line -match "Target:.*git") {
        $target = $line -replace "^\s*Target:\s*", ""
        Write-Host "Deleting credential: $target"
        cmdkey /delete:$target
    }
}
Write-Host "Done."
