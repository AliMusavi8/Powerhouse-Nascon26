#!/bin/sh
# Co-stream compositor. Reads the session layout from the API and mixes the participants' live feeds with
# ffmpeg xstack into rtsp://localhost:8554/costream/<id>. MediaMTX owns this process: it is restarted on
# host handoff (the API kicks the path) and stopped when nobody watches, so no ffmpeg is ever orphaned.
SID="$1"; OUT="rtsp://localhost:8554/$2"
LAYOUT_JSON=$(wget -q -O- "http://api:8080/internal/costream/$SID/layout") || exit 1
LAYOUT=$(echo "$LAYOUT_JSON" | sed -n 's/.*"layout":"\([a-z_0-9]*\)".*/\1/p')
KEYS=$(echo "$LAYOUT_JSON" | grep -o '"stream_key":[^,}]*' | sed 's/"stream_key"://; s/"//g')
INPUTS=""; N=0
for K in $KEYS; do
  if [ "$K" != "null" ] && wget -q --spider "http://localhost:8888/live/$K/index.m3u8" 2>/dev/null; then
    INPUTS="$INPUTS -rtsp_transport tcp -i rtsp://localhost:8554/live/$K"
  else
    INPUTS="$INPUTS -f lavfi -re -i color=c=0x0b5d2a:s=640x360:r=25"
  fi
  N=$((N+1))
done
[ "$N" -eq 0 ] && exit 1
case "$LAYOUT:$N" in
  *:1|solo:*) FILTER="[0:v]scale=1280:720[v]" ;;
  grid_2:*|*:2) FILTER="[0:v]scale=640:720[a];[1:v]scale=640:720[b];[a][b]hstack=inputs=2[v]" ;;
  spotlight:*) FILTER="[0:v]scale=960:720[m];"; S=""; i=1
    while [ $i -lt $N ]; do FILTER="$FILTER[$i:v]scale=320:240[s$i];"; S="$S[s$i]"; i=$((i+1)); done
    if [ $N -eq 2 ]; then FILTER="$FILTER${S}pad=320:720[side];"; else FILTER="$FILTER${S}vstack=inputs=$((N-1)),pad=320:720[side];"; fi
    FILTER="$FILTER[m][side]hstack=inputs=2[v]" ;;
  *) FILTER=""; L=""; i=0
    while [ $i -lt 4 ]; do
      if [ $i -lt $N ]; then FILTER="$FILTER[$i:v]scale=640:360[t$i];"; else FILTER="${FILTER}color=c=black:s=640x360:r=25[t$i];"; fi
      L="$L[t$i]"; i=$((i+1))
    done
    FILTER="$FILTER${L}xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0[v]" ;;
esac
exec ffmpeg -hide_banner -loglevel warning $INPUTS -filter_complex "$FILTER" -map "[v]" \
  -c:v libx264 -preset ultrafast -tune zerolatency -g 25 -b:v 2000k -f rtsp -rtsp_transport tcp "$OUT"
