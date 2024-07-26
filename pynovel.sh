#!/bin/sh
config_file="$HOME/.config/pynovel/pynovel_config.sh"
pynovel_editor=${VISUAL:-${EDITOR}}
images_cache_dir="/tmp/pynovel/pynovel-images" #used for temporarily storing book covers

if printf "%s" "$*" | grep -qE "\-\-edit|\-e" 2>/dev/null; then
    . "${config_file}"
    [ -z "$pynovel_editor" ] && pynovel_editor="nano"
    "$pynovel_editor" "$config_file"
    exit 0
fi

python main.py
