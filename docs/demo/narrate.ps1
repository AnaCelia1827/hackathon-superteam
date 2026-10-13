param(
    [Parameter(Mandatory = $true)][string]$SceneFile,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$scenes = Get-Content -LiteralPath $SceneFile -Raw -Encoding UTF8 | ConvertFrom-Json
$voice = New-Object -ComObject SAPI.SpVoice
$voice.Voice = $voice.GetVoices('Name=Microsoft Zira Desktop').Item(0)
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
for ($i = 0; $i -lt $scenes.Count; $i++) {
    $stream = New-Object -ComObject SAPI.SpFileStream
    $path = Join-Path $OutputDirectory ('scene-{0:d2}.wav' -f $i)
    $stream.Open($path, 3, $false)
    $voice.AudioOutputStream = $stream
    [void]$voice.Speak($scenes[$i].voice)
    $stream.Close()
    Write-Output $path
}
