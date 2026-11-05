# PhoneCam

Usa la cámara de tu teléfono Android como webcam en Windows, sin marca de agua y sin límite de resolución.
Proyecto de uso personal.

```
 Teléfono (app Flutter)                       PC Windows (receptor Python)
 ┌──────────────────────┐   Wi-Fi o USB      ┌─────────────────────────────┐
 │ Cámara → codificador │  ── WebRTC ──────▶ │ decodifica → ajusta 16:9 →  │ → Zoom / Meet /
 │ por hardware (H.264/ │   (video UDP)      │ cámara virtual (OBS driver) │   OBS / Discord
 │ VP8)                 │ ◀─ señalización ── │ anuncio mDNS + QR           │
 └──────────────────────┘   WebSocket :8765  └─────────────────────────────┘
```

## Qué resuelve frente a DroidCam

| Problema | Cómo lo resuelve PhoneCam |
|---|---|
| Conexión complicada | La PC se anuncia sola en la red (mDNS): abres la app y la PC aparece en la lista. Si tu router bloquea mDNS, escaneas el QR que muestra la PC. Si se corta la conexión, se reconecta sola. |
| Calidad limitada | 720p, 1080p o 4K, a 30 o 60 fps, con bitrate de hasta 25 Mbps. La salida de la cámara virtual se configura aparte (de HD a 4K). |
| Marca de agua | No tiene. |

## Lo que necesitas instalar

**En la PC (para usar el receptor):**
1. [Python 3.11 o 3.12](https://www.python.org/downloads/). Marca "Add Python to PATH" al instalar.
2. [OBS Studio 30 o más reciente](https://obsproject.com/). Solo se usa su driver de cámara virtual; no hace falta abrir OBS.

**Para compilar la app Android** (elige una opción):
- **Opción A, en tu PC:** [Git](https://git-scm.com/), el [SDK de Flutter](https://docs.flutter.dev/get-started/install/windows/mobile) y [Android Studio](https://developer.android.com/studio).
- **Opción B, sin instalar nada:** sube este repositorio a GitHub. El flujo `.github/workflows/build.yml` compila el APK y el .exe; los descargas desde la pestaña *Actions*.

### Compilar con GitHub (Opción B)
1. Crea un repositorio vacío en [github.com/new](https://github.com/new) (sin README ni .gitignore).
2. Desde esta carpeta:
   ```bat
   git remote add origin https://github.com/TU_USUARIO/phonecam.git
   git push -u origin main
   ```
3. En la pestaña **Actions** se ejecuta `build` (unos 10 minutos). Al terminar, abajo en *Artifacts* están:
   - **PhoneCam-Android**: el APK para el teléfono.
   - **PhoneCam-Windows**: la carpeta con `PhoneCam.exe` y `allow_firewall.bat` (no necesita Python).
4. Para una descarga permanente (los *Artifacts* caducan a los 90 días y piden iniciar sesión), crea una versión:
   ```bat
   git tag v0.1.0
   git push --tags
   ```
   Se publica en **Releases** con `PhoneCam-Android.apk` y `PhoneCam-Windows.zip`.

**Firma del APK.** Para que cada versión nueva se instale encima de la anterior, el APK se firma siempre con la misma clave. Va en *Settings → Secrets and variables → Actions* del repositorio:
- `ANDROID_KEYSTORE_BASE64`: el archivo `.jks` en base64.
- `ANDROID_KEYSTORE_PASSWORD`: su contraseña (alias `phonecam`).

Sin esos secretos, los builds normales se firman con una clave de depuración y los tags fallan. **Guarda una copia del `.jks` y su contraseña:** si se pierden, las actualizaciones obligan a desinstalar la app.

Con la versión `.exe` solo hace falta OBS Studio en la PC: descomprime el zip, ejecuta `allow_firewall.bat` como administrador una vez, y abre `PhoneCam.exe`.

## Paso a paso

### 1. Receptor en la PC
```bat
cd receiver
run.bat
```
La primera vez instala las dependencias en `.venv`. Se abre una ventana con el estado, la IP y un QR.
Después, ejecuta **una sola vez** `allow_firewall.bat` como administrador y comprueba que tu Wi-Fi esté marcada como red **Privada** en Windows.

En Zoom, Meet, Discord u OBS, elige la cámara **"OBS Virtual Camera"**.

Para tener un `.exe` que no necesite Python: ejecuta `build_exe.bat` y se genera `receiver\dist\PhoneCam\PhoneCam.exe`.

### 2. App en el teléfono
```bat
cd mobile
python tool\setup_android.py
flutter build apk --release
```
El APK queda en `mobile\build\app\outputs\flutter-apk\app-release.apk`. Cópialo al teléfono e instálalo (hay que permitir "instalar apps desconocidas").
Otra forma: activa la *depuración USB* en el teléfono, conéctalo y ejecuta `flutter run --release`.

### 3. Usarlo
Abre PhoneCam en la PC y luego la app en el teléfono. Toca tu PC en la lista y listo.
Pon el teléfono en **horizontal** para llenar el cuadro 16:9. En vertical se ve completo con barras negras, o recortado si eliges "Recortar" en la PC.

### Por cable USB (sin Wi-Fi o para menos latencia)
Conecta el cable y activa en el teléfono **Ajustes → Red → Zona Wi-Fi / Anclaje → Anclaje USB**.
Así el teléfono y la PC quedan en una mini red por cable y todo funciona igual (se puede usar "IP manual" con la IP que muestre la ventana de la PC).
No hace falta ADB ni drivers.

## Solución de problemas
- **La PC no aparece en la lista:** usa "Escanear QR". Si tampoco conecta, revisa el firewall (`allow_firewall.bat`) y que la red sea Privada. Algunas redes públicas o de invitados aíslan los dispositivos entre sí.
- **"Cámara virtual: ..." en la ventana de la PC:** instala o actualiza OBS Studio. Si otra app ya está usando la OBS Virtual Camera (por ejemplo, OBS con la cámara virtual activada), ciérrala.
- **Registro de errores:** `%APPDATA%\PhoneCam\phonecam.log`.
- **Probar sin teléfono:** `run.bat --output preview`, y en otra consola `.venv\Scripts\python tools\fake_phone.py`.

## Estructura
```
receiver/                 Receptor Windows (Python)
  phonecam_receiver/
    server.py             WebSocket de señalización + WebRTC (aiortc)
    output.py             pipeline de frames → cámara virtual (pyvirtualcam), ajuste 16:9
    discovery.py          anuncio mDNS y datos del QR
    gui.py                ventana (tkinter)
  tools/fake_phone.py     teléfono simulado para pruebas
mobile/                   App Flutter (Android; iOS en el futuro)
  lib/services/streamer.dart   cámara + WebRTC + reconexión automática
  lib/services/discovery.dart  descubrimiento mDNS
  tool/setup_android.py        genera android/ y aplica permisos
```

## Ideas para después
- Cámara virtual nativa de Windows 11 (MediaFoundation), para no depender de OBS.
- Micrófono del teléfono como entrada de audio.
- Zoom, enfoque, linterna y exposición desde la app.
- Versión para iPhone (requiere una Mac para compilar).
