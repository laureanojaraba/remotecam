"""Genera la carpeta android/ con `flutter create` y aplica los permisos y ajustes
que necesita PhoneCam. Se puede ejecutar varias veces sin problema.

Uso (desde la carpeta mobile/):  python tool/setup_android.py
"""

import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PERMISSIONS = [
    "android.permission.CAMERA",
    "android.permission.INTERNET",
    "android.permission.ACCESS_NETWORK_STATE",
    "android.permission.ACCESS_WIFI_STATE",
    "android.permission.CHANGE_WIFI_MULTICAST_STATE",
    "android.permission.WAKE_LOCK",
]


def run(*cmd: str) -> None:
    exe = shutil.which(cmd[0])
    if not exe:
        sys.exit(f"No encuentro '{cmd[0]}' en el PATH. ¿Instalaste Flutter?")
    print("+", " ".join(cmd))
    subprocess.run([exe, *cmd[1:]], cwd=ROOT, check=True)


def patch_manifest() -> None:
    p = ROOT / "android/app/src/main/AndroidManifest.xml"
    s = p.read_text(encoding="utf-8")
    missing = [perm for perm in PERMISSIONS if perm not in s]
    if missing:
        lines = "".join(f'    <uses-permission android:name="{perm}" />\n' for perm in missing)
        s = s.replace("    <application", lines + "    <application", 1)
    if "usesCleartextTraffic" not in s:
        s = s.replace("<application", '<application\n        android:usesCleartextTraffic="true"', 1)
    s = re.sub(r'android:label="[^"]*"', 'android:label="PhoneCam"', s, count=1)
    p.write_text(s, encoding="utf-8")
    print("✓ AndroidManifest.xml")


def patch_gradle() -> None:
    for name in ("build.gradle.kts", "build.gradle"):
        p = ROOT / "android/app" / name
        if not p.exists():
            continue
        s = p.read_text(encoding="utf-8")
        s2 = re.sub(r"minSdk(Version)?\s*=?\s*flutter\.minSdkVersion", lambda m: f"minSdk{m.group(1) or ''} = 24", s)
        if s2 != s:
            p.write_text(s2, encoding="utf-8")
        print(f"✓ {name} (minSdk 24)")
        return
    print("! No encontré build.gradle de la app; revisa minSdk manualmente (>= 24)")


def main() -> None:
    if not (ROOT / "android").exists():
        run("flutter", "create", "--platforms=android", "--org", "com.personal.phonecam",
            "--project-name", "phonecam", ".")
        # flutter create agrega un test de ejemplo que no aplica a esta app
        (ROOT / "test/widget_test.dart").unlink(missing_ok=True)
    patch_manifest()
    patch_gradle()
    run("flutter", "pub", "get")
    print("\nListo. Conecta el teléfono con depuración USB y ejecuta:  flutter run --release")
    print("o genera el APK con:  flutter build apk --release")


if __name__ == "__main__":
    main()
