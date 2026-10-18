# Downloads the playback builds linked by mpv.io and ffmpeg.org.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$vendor = Join-Path $root 'vendor/windows'
New-Item -ItemType Directory -Force $vendor | Out-Null
$temp = Join-Path ([IO.Path]::GetTempPath()) ('firemedia-playback-' + [guid]::NewGuid())
New-Item -ItemType Directory $temp | Out-Null
try {
    $headers = @{ Accept = 'application/vnd.github+json'; 'User-Agent' = 'FireMedia-build' }
    # Scope authentication to the GitHub API; never forward it to binary hosts.
    if ($env:GH_TOKEN) { $headers.Authorization = "Bearer $env:GH_TOKEN" }
    $release = Invoke-RestMethod 'https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest' -Headers $headers
    $asset = @($release.assets | Where-Object { $_.name -match '^mpv-dev-x86_64-\d.*\.7z$' })
    if ($asset.Count -ne 1) { throw 'No unambiguous baseline x64 libmpv build found.' }
    $asset = $asset[0]
    $mpvArchive = Join-Path $temp 'libmpv.7z'
    Invoke-WebRequest -UseBasicParsing $asset.browser_download_url -OutFile $mpvArchive
    if ($asset.digest -match '^sha256:(.+)$') {
        if ((Get-FileHash $mpvArchive -Algorithm SHA256).Hash -ne $Matches[1]) { throw 'libmpv download hash mismatch.' }
    }
    $mpv = Join-Path $temp 'mpv'; New-Item -ItemType Directory $mpv | Out-Null
    # Windows tar uses libarchive, which supports reading 7z archives.
    tar.exe -xf $mpvArchive -C $mpv
    if ($LASTEXITCODE -ne 0) { throw 'Could not unpack libmpv. Extract the .7z with 7-Zip into vendor/windows instead.' }
    $mpvDlls = @(Get-ChildItem $mpv -Recurse -Filter '*.dll')
    if (-not ($mpvDlls | Where-Object { $_.Name -match '^(libmpv-2|mpv-2|mpv-1)\.dll$' })) { throw 'The archive did not contain a supported libmpv DLL.' }
    $mpvDlls | Copy-Item -Destination $vendor -Force

    $ffmpegUrl = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
    $ffmpegArchive = Join-Path $temp 'ffmpeg.zip'
    Invoke-WebRequest -UseBasicParsing $ffmpegUrl -OutFile $ffmpegArchive
    $expected = (Invoke-WebRequest -UseBasicParsing ($ffmpegUrl + '.sha256')).Content
    if ($expected -is [byte[]]) { $expected = [Text.Encoding]::UTF8.GetString($expected) }
    $expected = ([string]$expected).Trim().Split(' ')[0]
    if ($expected -notmatch '^[a-fA-F0-9]{64}$' -or (Get-FileHash $ffmpegArchive -Algorithm SHA256).Hash -ne $expected) { throw 'FFmpeg download hash mismatch.' }
    $ffmpeg = Join-Path $temp 'ffmpeg'; Expand-Archive $ffmpegArchive -DestinationPath $ffmpeg
    $executable = @(Get-ChildItem $ffmpeg -Recurse -Filter 'ffmpeg.exe')
    if ($executable.Count -ne 1) { throw 'No unambiguous ffmpeg.exe found.' }
    Copy-Item $executable[0].FullName -Destination $vendor -Force
    $licenses = Join-Path $vendor 'licenses'; New-Item -ItemType Directory -Force $licenses | Out-Null
    foreach ($entry in @(@('mpv', $mpv), @('ffmpeg', $ffmpeg))) {
        $destination = Join-Path $licenses $entry[0]; New-Item -ItemType Directory -Force $destination | Out-Null
        Get-ChildItem $entry[1] -Recurse -File | Where-Object { $_.Name -match '(?i)^(license|copying|copyright|readme)' } | ForEach-Object {
            $relative = $_.FullName.Substring($entry[1].Length).TrimStart([char[]]"\/")
            $target = Join-Path $destination $relative
            New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
            Copy-Item $_.FullName $target -Force
        }
    }
    @"
libmpv release: $($release.tag_name)
libmpv binary: $($asset.browser_download_url)
libmpv source/build scripts: https://github.com/shinchiro/mpv-winbuild-cmake
mpv source: https://github.com/mpv-player/mpv
FFmpeg binary: $ffmpegUrl
FFmpeg binary SHA256: $expected
FFmpeg build/source information: https://www.gyan.dev/ffmpeg/builds/
FFmpeg source: https://ffmpeg.org/download.html
Review upstream notices and provide corresponding source for public redistribution.
"@ | Set-Content (Join-Path $licenses 'playback-builds.txt')
    Write-Host 'Playback dependencies are ready. Run packaging/windows/build.ps1 next.'
} finally {
    Remove-Item $temp -Recurse -Force
}
