#!/bin/sh
# Guest-player feed for a match: a branded live slate that keeps the HLS/WHEP URL playable with no broadcaster.
OUT="rtsp://localhost:8554/$2"
exec ffmpeg -hide_banner -loglevel warning -re -f lavfi -i "testsrc2=s=1280x720:r=25" \
  -vf "drawbox=y=600:w=iw:h=120:color=0x0b5d2a@0.9:t=fill" \
  -c:v libx264 -preset ultrafast -tune zerolatency -g 25 -b:v 1500k -f rtsp -rtsp_transport tcp "$OUT"
