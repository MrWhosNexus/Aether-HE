#!/bin/sh
# Aether HE launcher (Flatpak). WebKit's DMABUF renderer is unreliable on some
# GPUs (notably NVIDIA) inside the sandbox; disabling it avoids a black window.
export WEBKIT_DISABLE_DMABUF_RENDERER=1
export GDK_BACKEND="${GDK_BACKEND:-wayland,x11}"
cd /app/share/aether || exit 1
exec python3 app_web.py "$@"
