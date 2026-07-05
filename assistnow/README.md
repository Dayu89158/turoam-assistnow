TuRoam AssistNow Files

This directory is automatically updated by GitHub Actions.

Raw URLs for Firmware

Manifest
https://raw.githubusercontent.com/Dayu89158/turoam-assistnow/refs/heads/main/assistnow/assistnow_manifest.json
AssistNow UBX
https://raw.githubusercontent.com/Dayu89158/turoam-assistnow/refs/heads/main/assistnow/assistnow.ubx
Latest
https://raw.githubusercontent.com/Dayu89158/turoam-assistnow/refs/heads/main/assistnow/latest.txt
Files
assistnow.ubx: u-blox AssistNow UBX data.
assistnow_manifest.json: metadata for firmware validation.
latest.txt: compact metadata for quick checking.
Firmware Logic

The firmware should download assistnow_manifest.json first.

If the flash-stored AssistNow data matches:

size
crc32
valid_until_utc
assist_type

and the current trusted UTC is less than or equal to valid_until_utc, the firmware should reuse the flash copy and skip downloading assistnow.ubx.

If validation fails, the firmware should download assistnow.ubx, verify size and CRC32 against the manifest, then write it to flash.

Current Assist Type
predictive_orbits_1day
Notes

The u-blox download URL is stored in GitHub Actions Secrets as:

ASSISTNOW_DOWNLOAD_URL
