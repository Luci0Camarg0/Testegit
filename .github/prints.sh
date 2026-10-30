#!/bin/bash
# Instala o app no emulador, abre cada aba e tira prints.
set -x
mkdir -p prints
adb push amostras/*.jpg /sdcard/Pictures/
adb push amostras/*.mp3 /sdcard/Music/
adb shell content call --method scan_volume --uri content://media --arg external_primary
sleep 5
adb install -r GaleriaPlus.apk | tee prints/instalacao.txt
for p in READ_MEDIA_IMAGES READ_MEDIA_VIDEO READ_MEDIA_AUDIO; do
  adb shell pm grant com.galeria.app android.permission.$p
done
adb logcat -c
adb shell am start -W -n com.galeria.app/.MainActivity
sleep 10
adb exec-out screencap -p > prints/1-fotos.png
size=$(adb shell wm size | grep -o '[0-9]*x[0-9]*' | tail -1)
w=${size%x*}; h=${size#*x}
navy=$((h - h * 9 / 100))
adb shell input tap $((w / 2)) $navy; sleep 4
adb exec-out screencap -p > prints/2-musicas.png
adb shell input tap $((w / 2)) $((h * 30 / 100)); sleep 4
adb exec-out screencap -p > prints/3-tocando.png
adb shell input tap $((w * 5 / 6)) $navy; sleep 4
adb exec-out screencap -p > prints/4-notas.png
adb logcat -d -b crash > prints/crash.txt
adb shell pidof com.galeria.app && echo "app aberto" > prints/status.txt || echo "app fechou" > prints/status.txt
exit 0
