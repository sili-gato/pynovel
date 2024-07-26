#!/bin/sh
config_file="$HOME/.config/pynovel/pynovel_config.sh"
pynovel_editor=${VISUAL:-${EDITOR}}
images_cache_dir="/tmp/pynovel/pynovel-images" #used for temporarily storing book covers

if printf "%s" "$*" | grep -qE "\-\-edit|\-e" 2>/dev/null; then
    #shellcheck disable=1090
    [ -f "$config_file" ] || pip install -r $(dirname "$0")/requirements.txt || touch "$config_file" &&
    . "${config_file}"
    [ -z "$pynovel_editor" ] && pynovel_editor="nano"
    "$pynovel_editor" "$config_file"
    exit 0
fi

configuration() {
    [ -n "$XDG_CONFIG_HOME" ] && config_dir="$XDG_CONFIG_HOME/pynovel" || config_dir="$HOME/.config/pynovel"
    [ -n "$XDG_DATA_HOME" ] && data_dir="$XDG_DATA_HOME/pynovel" || data_dir="$HOME/.local/share/pynovel"
    [ ! -d "$config_dir" ] && mkdir -p "$config_dir"
    [ -f "$config_file" ] && . "${config_file}"
    [ -z "$download_dir" ] && download_dir="$PWD"
}

configuration

python $(dirname "$0")/main.py $download_dir
