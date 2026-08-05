# launch_emulators.ps1
# Lanza los AVDs nombrados (uno por rol de carpool) con Google Play.
#
# Uso:
#   .\launch_emulators.ps1           # lanza los 4
#   .\launch_emulators.ps1 -Count 1  # smoke test con un dispositivo
#   .\launch_emulators.ps1 -WipeData # arranca limpiando datos del AVD
#
# Puertos ADB:
#   emulator-5554  LL_conductor
#   emulator-5556  LL_pasajero1
#   emulator-5558  LL_pasajero2
#   emulator-5560  LL_pasajero3

param(
    [int]$Count = 4,
    [int]$MemoryMB = 768,
    [switch]$WipeData
)

$AndroidHome = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { 'C:\Android\Sdk' }
$EmulatorExe = Join-Path $AndroidHome 'emulator\emulator.exe'
$AdbExe      = Join-Path $AndroidHome 'platform-tools\adb.exe'

if (-not (Test-Path $EmulatorExe)) { Write-Error ('Emulador no encontrado: ' + $EmulatorExe); exit 1 }
if (-not (Test-Path $AdbExe))      { Write-Error ('ADB no encontrado: ' + $AdbExe); exit 1 }

$Avds = @(
    @{ Name = 'LL_conductor';  Port = 5554; Label = 'conductor-lemoa'     },
    @{ Name = 'LL_pasajero1';  Port = 5556; Label = 'pasajero-amorebieta' },
    @{ Name = 'LL_pasajero2';  Port = 5558; Label = 'pasajero-durango'    },
    @{ Name = 'LL_pasajero3';  Port = 5560; Label = 'pasajero-eibar'      }
)
$Avds = $Avds | Select-Object -First $Count

Write-Host ('=== LocationLab - Lanzando ' + $Count + ' emulador(es) con Google Play ===')
Write-Host ('  RAM/emu : ' + $MemoryMB + ' MB  |  RAM total: ' + ($Count * $MemoryMB) + ' MB')
Write-Host ''

foreach ($avd in $Avds) {
    Write-Host ('  Lanzando ' + $avd.Name + ' (' + $avd.Label + ') en puerto ' + $avd.Port + '...')

    $emuArgs = @(
        '-avd',    $avd.Name,
        '-port',   $avd.Port,
        '-memory', $MemoryMB,
        '-no-boot-anim',
        '-no-snapshot',
        '-no-audio',
        '-gpu',    'swiftshader_indirect'
    )

    if ($WipeData) {
        # Limpia datos solo cuando se pide explicitamente.
        $emuArgs += '-wipe-data'
    }

    Start-Process -FilePath $EmulatorExe -ArgumentList $emuArgs -PassThru -WindowStyle Minimized | Out-Null
    Start-Sleep -Seconds 2
}

Write-Host ''
Write-Host 'Emuladores lanzados. Esperando que arranquen (~90 s)...'
Write-Host ''

$Timeout = 150
$Elapsed = 0

while ($Elapsed -lt $Timeout) {
    Start-Sleep -Seconds 5
    $Elapsed += 5
    $Ready = (& $AdbExe devices 2>&1 | Select-String 'emulator.*device').Count
    Write-Host ('  [' + $Elapsed + ' s] Emuladores listos: ' + $Ready + '/' + $Count)
    if ($Ready -ge $Count) { break }
}

if ($Elapsed -ge $Timeout) {
    Write-Warning 'Timeout. Algunos emuladores pueden no estar listos aun.'
} else {
    Write-Host ''
    Write-Host 'Todos los emuladores listos.'
}

Write-Host ''
Write-Host 'Siguiente paso: detecta los dispositivos ADB e inyecta GPS'
Write-Host '  python inject_gps.py --detect'
