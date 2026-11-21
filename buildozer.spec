[app]
title = Jarvis
package.name = jarvis
package.domain = org.iskander

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.exclude_dirs = server,.github,bin,.buildozer

version = 1.0
icon.filename = %(source.dir)s/icon.png
requirements = python3==3.11.5,hostpython3==3.11.5,kivy==2.3.0,openssl,certifi

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,READ_EXTERNAL_STORAGE,READ_MEDIA_IMAGES
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
