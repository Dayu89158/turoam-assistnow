import json
import os
import sys
import time
import zlib
from pathlib import Path

import requests


OUT_DIR = Path("assistnow")
UBX_FILE = OUT_DIR / "assistnow.ubx"
MANIFEST_FILE = OUT_DIR / "assistnow_manifest.json"
LATEST_FILE = OUT_DIR / "latest.txt"


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def ubx_checksum(frame_body: bytes) -> tuple[int, int]:
    ck_a = 0
    ck_b = 0
    for b in frame_body:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return ck_a, ck_b


def validate_ubx_stream(data: bytes) -> dict:
    pos = 0
    frames = 0
    mga_frames = 0

    if len(data) < 8:
        fail(f"UBX file too small: {len(data)} bytes")

    while pos < len(data):
        if pos + 8 > len(data):
            fail(f"Truncated UBX frame header at offset {pos}")

        if data[pos] != 0xB5 or data[pos + 1] != 0x62:
            fail(f"Invalid UBX sync at offset {pos}, bytes={data[pos:pos+8].hex(' ').upper()}")

        cls = data[pos + 2]
        msg_id = data[pos + 3]
        length = data[pos + 4] | (data[pos + 5] << 8)

        frame_len = 6 + length + 2
        end = pos + frame_len

        if end > len(data):
            fail(f"Truncated UBX payload at offset {pos}, length={length}")

        body = data[pos + 2 : pos + 6 + length]
        ck_a, ck_b = ubx_checksum(body)

        got_a = data[pos + 6 + length]
        got_b = data[pos + 6 + length + 1]

        if ck_a != got_a or ck_b != got_b:
            fail(
                f"UBX checksum failed at offset {pos}, "
                f"class=0x{cls:02X}, id=0x{msg_id:02X}, "
                f"calc={ck_a:02X} {ck_b:02X}, got={got_a:02X} {got_b:02X}"
            )

        frames += 1

        # UBX-MGA class = 0x13
        if cls == 0x13:
            mga_frames += 1

        pos = end

    if frames <= 0:
        fail("No UBX frames found")

    if mga_frames <= 0:
        fail("No UBX-MGA frames found; this may not be AssistNow data")

    return {
        "frames": frames,
        "mga_frames": mga_frames,
    }


def main() -> None:
    url = os.environ.get("ASSISTNOW_DOWNLOAD_URL", "").strip()
    if not url:
        fail("ASSISTNOW_DOWNLOAD_URL is empty")

        valid_hours = int(os.environ.get("ASSISTNOW_VALID_HOURS", "30"))
    assist_type = os.environ.get("ASSISTNOW_TYPE", "predictive_orbits_1day").strip()
    min_remaining_hours = int(os.environ.get("ASSISTNOW_MIN_REMAINING_HOURS", "8"))

    if valid_hours <= 0:
        fail("ASSISTNOW_VALID_HOURS must be positive")

    if min_remaining_hours < 0:
        fail("ASSISTNOW_MIN_REMAINING_HOURS must be >= 0")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Avoid consuming u-blox / Thingstream request quota when the existing
    # AssistNow data in the repository is still fresh enough.
    if MANIFEST_FILE.exists() and UBX_FILE.exists():
        try:
            old = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
            old_valid_until = int(old.get("valid_until_utc", 0))
            old_size = int(old.get("size", 0))
            old_crc32 = str(old.get("crc32", "")).upper().strip()
            now_utc = int(time.time())
            remaining_sec = old_valid_until - now_utc

            if (
                remaining_sec > min_remaining_hours * 3600
                and old_size > 0
                and old_crc32
            ):
                print("Existing AssistNow is still fresh enough.")
                print(f"remaining_hours={remaining_sec / 3600:.2f}")
                print(f"valid_until_utc={old_valid_until}")
                print(f"size={old_size}")
                print(f"crc32={old_crc32}")
                print("Skip u-blox download to avoid request quota consumption.")
                return
        except Exception as e:
            print(f"Existing manifest check failed, will download again: {e}")

    print("Downloading AssistNow UBX...")
    resp = requests.get(url, timeout=60)

    if resp.status_code != 200:
        fail(f"Download failed, HTTP {resp.status_code}: {resp.text[:300]}")

    data = resp.content

    # 防止下载到 HTML / JSON 错误页
    head = data[:64].lower()
    if b"<html" in head or b"<!doctype" in head or head.strip().startswith(b"{"):
        fail(f"Downloaded data does not look like raw UBX, first64={data[:64]!r}")

    stats = validate_ubx_stream(data)

    size = len(data)
    crc32 = zlib.crc32(data) & 0xFFFFFFFF

    generated_utc = int(time.time())
    valid_from_utc = generated_utc
    valid_until_utc = generated_utc + valid_hours * 3600

    UBX_FILE.write_bytes(data)

    manifest = {
        "schema": "turoam-assistnow-manifest-v1",
        "file": "assistnow.ubx",
        "version": 1,
        "assist_type": assist_type,
        "generated_utc": generated_utc,
        "valid_from_utc": valid_from_utc,
        "valid_until_utc": valid_until_utc,
        "valid_hours": valid_hours,
        "size": size,
        "crc32": f"{crc32:08X}",
        "ubx_frames": stats["frames"],
        "mga_frames": stats["mga_frames"],
        "source": "github_actions_ublox_assistnow"
    }

    MANIFEST_FILE.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    LATEST_FILE.write_text(
        f"{generated_utc},{valid_until_utc},{size},{crc32:08X}\n",
        encoding="utf-8",
    )

    print("AssistNow updated.")
    print(f"assist_type={assist_type}")
    print(f"size={size}")
    print(f"crc32={crc32:08X}")
    print(f"frames={stats['frames']}")
    print(f"mga_frames={stats['mga_frames']}")
    print(f"generated_utc={generated_utc}")
    print(f"valid_until_utc={valid_until_utc}")


if __name__ == "__main__":
    main()
