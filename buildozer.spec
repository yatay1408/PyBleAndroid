[app]
title = ble
package.name = ble
package.domain = org.test
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = python3,kivy,bleak
orientation = portrait

# Kivy version to use
osx.kivy_version = 2.2.0

# Android specific
fullscreen = 0
android.api = 30
android.minapi = 21
android.sdk = 30
android.ndk = 23b
android.ndk_api = 21

# Required permissions for BLE
android.permissions = android.permission.INTERNET, android.permission.BLUETOOTH, android.permission.BLUETOOTH_ADMIN, android.permission.ACCESS_FINE_LOCATION, android.permission.ACCESS_COARSE_LOCATION

# The Android archs to build for
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True
android.debug_artifact = apk

[buildozer]
log_level = 2
warn_on_root = 1
