# setup_avds.ps1
# Ejecutar DESPUES de que Android Studio termine de instalar.
# Configura 4 AVDs ligeros y el PATH del SDK.
#
# Uso:
#   .\setup_avds.ps1          # crea 4 AVDs
#   .\setup_avds.ps1 -Count 1 # crea solo 1 AVD (para prueba rapida)

param([int]$Count = 4)

# ── Localizar SDK ──────────────────────────────────────────────────────────────
$sdkRoots = @(
    "$env:LOCALAPPDATA\Android\Sdk",
    "C:\Android\Sdk",
    "$env:USERPROFILE\AppData\Local\Android\Sdk"
)

$sdkRoot = $null
foreach ($r in $sdkRoots) {
    if (Test-Path "$r\cmdline-tools") { $sdkRoot = $r; break }
    if (Test-Path "$r\platform-tools") { $sdkRoot = $r; break }
}

if (-not $sdkRoot) {
    # Buscar sdkmanager.bat en disco
    $found = Get-ChildItem -Path "C:\", "$env:LOCALAPPDATA" -Recurse -Filter "sdkmanager.bat" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $sdkRoot = $found.Directory.Parent.Parent.FullName }
}

if (-not $sdkRoot) {
    Write-Error "SDK de Android no encontrado. Abre Android Studio una vez para completar la instalacion del SDK."
    exit 1
}

Write-Host "SDK encontrado en: $sdkRoot"

# Localizar sdkmanager y avdmanager
$sdkmanager = Get-ChildItem -Path $sdkRoot -Recurse -Filter "sdkmanager.bat" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
$avdmanager = Get-ChildItem -Path $sdkRoot -Recurse -Filter "avdmanager.bat" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
$emulator   = "$sdkRoot\emulator\emulator.exe"
$adb        = "$sdkRoot\platform-tools\adb.exe"

if (-not $sdkmanager) { Write-Error "sdkmanager no encontrado. Instala Android Studio primero."; exit 1 }

# ── Añadir SDK al PATH ─────────────────────────────────────────────────────────
$pathAdditions = @(
    "$sdkRoot\platform-tools",
    "$sdkRoot\emulator",
    "C:\Android\platform-tools"  # el que instalamos antes via platform-tools-latest
)
foreach ($p in $pathAdditions) {
    if ((Test-Path $p) -and ($env:PATH -notlike "*$p*")) {
        [Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";$p", "User")
        $env:PATH += ";$p"
        Write-Host "Añadido al PATH: $p"
    }
}

$env:ANDROID_HOME = $sdkRoot
[Environment]::SetEnvironmentVariable("ANDROID_HOME", $sdkRoot, "User")
Write-Host "ANDROID_HOME = $sdkRoot"

# ── Instalar componentes SDK ───────────────────────────────────────────────────
Write-Host "`n=== Instalando componentes SDK ==="

# Aceptar licencias automáticamente
Write-Host "Aceptando licencias..."
"y`ny`ny`ny`ny`ny`ny" | & $sdkmanager --licenses 2>&1 | Out-Null

# Instalar imagen del sistema (ligera: API 33, sin Google APIs, x86_64)
$image = "system-images;android-33;default;x86_64"
Write-Host "Instalando $image (~800 MB, puede tardar varios minutos)..."
& $sdkmanager $image "platform-tools" "emulator" 2>&1

# ── Crear AVDs ─────────────────────────────────────────────────────────────────
Write-Host "`n=== Creando $Count AVDs ==="

$avdNames = @("conductor", "pasajero1", "pasajero2", "pasajero3")

for ($i = 0; $i -lt $Count; $i++) {
    $avdName = "LL_$($avdNames[$i])"
    Write-Host "  Creando AVD: $avdName ..."

    # Borrar si ya existe
    & $avdmanager delete avd --name $avdName 2>&1 | Out-Null

    "no" | & $avdmanager create avd `
        --name $avdName `
        --package $image `
        --device "pixel_7" `
        --force 2>&1

    Write-Host "  OK: $avdName creado"
}

# ── Actualizar emulator_config.json ───────────────────────────────────────────
$cfgPath = "emulator_config.json"
if (Test-Path $cfgPath) {
    $cfg = Get-Content $cfgPath | ConvertFrom-Json
    $deviceMap = @("conductor-lemoa", "pasajero-amorebieta", "pasajero-durango", "pasajero-eibar")
    $avdNameMap = @("conductor", "pasajero1", "pasajero2", "pasajero3")
    $serials = @("emulator-5554", "emulator-5556", "emulator-5558", "emulator-5560")

    $newMap = @()
    for ($i = 0; $i -lt [Math]::Min($Count, 4); $i++) {
        $newMap += [PSCustomObject]@{
            serial    = $serials[$i]
            device_id = $deviceMap[$i]
            avd_name  = "LL_$($avdNameMap[$i])"
            label     = $cfg.emulator_map[$i].label
        }
    }
    $cfg.emulator_map = $newMap
    $cfg | ConvertTo-Json -Depth 5 | Set-Content $cfgPath
    Write-Host "`nActualizado emulator_config.json"
}

# ── Instrucciones finales ─────────────────────────────────────────────────────
Write-Host "`n======================================================="
Write-Host "  Setup completado. Ahora:"
Write-Host "======================================================="
Write-Host ""
Write-Host "1. Lanza los $Count emuladores:"
for ($i = 0; $i -lt $Count; $i++) {
    $port = 5554 + ($i * 2)
    $avd = "LL_$($avdNames[$i])"
    Write-Host "   Start-Process '$emulator' -ArgumentList '-avd $avd -port $port -memory 768 -no-boot-anim -no-audio -gpu swiftshader_indirect -no-snapshot'"
}
Write-Host ""
Write-Host "2. Espera ~60 s a que arranquen, luego:"
Write-Host "   python inject_gps.py --detect"
Write-Host "   python inject_gps.py --speed 30"
