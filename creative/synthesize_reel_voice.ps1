param(
    [Parameter(Mandatory = $true)][string]$Text,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$VoiceName = "Microsoft Tolga"
)

Add-Type -AssemblyName System.Speech
$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    try {
        $synth.SelectVoice($VoiceName)
    }
    catch {
        $turkish = $synth.GetInstalledVoices() |
            Where-Object { $_.VoiceInfo.Culture.Name -eq "tr-TR" } |
            Select-Object -First 1
        if ($null -eq $turkish) {
            throw "Turkish Windows voice was not found."
        }
        $synth.SelectVoice($turkish.VoiceInfo.Name)
    }
    $synth.Rate = 1
    $synth.Volume = 100
    $synth.SetOutputToWaveFile($OutputPath)
    $synth.Speak($Text)
}
finally {
    $synth.Dispose()
}
