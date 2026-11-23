# MTP sources and local integration

This library adds a Still Image / MTP interface to the existing Arduino USB OTG stack. It uses the filesystem already mounted at `/sdcard`; it never exports raw FAT blocks to the host.

Vendored sources (licenses retained alongside this file):

- [Espressif esp-usb](https://github.com/espressif/esp-usb/tree/68bf7f9613dbb1a31094fdb903209ae3e4bf388d/device/esp_tinyusb/mtp), commit `68bf7f9613dbb1a31094fdb903209ae3e4bf388d`, Apache-2.0: the `tinyusb_mtp*.c` files and `mtp/` headers.
- [TinyUSB MTP class](https://github.com/hathach/tinyusb/tree/702e55db3899885900b18c8d388a9cf92c624331/src/class/mtp), commit `702e55db3899885900b18c8d388a9cf92c624331`, MIT: `class/mtp/`.

Local changes are limited to Arduino 2.0.17 / IDF 4.4 / TinyUSB 0.16 compatibility and storage arbitration. `mtp_compat.h` supplies MTP configuration, the legacy FAT capacity query, and lifecycle hooks. The backend lifecycle acquires the shared recursive storage mutex before its own locks; the command callback checks application ownership before entering a filesystem operation. `ImuMtp.cpp` registers the custom class, handles reset/disconnect, and refuses web handoff while an MTP transaction, prepared upload or edit is outstanding.

`mtp_usb_compat.h` adapts endpoint APIs without replacing the USB core. The legacy ESP32-S3 DCD stall operation disables the endpoint and flushes its FIFO; clear-stall resets DATA0 and busy, and the adapter releases its old claim. Deferred functions are queued at the tail in TinyUSB 0.16; its endpoints have no RX_PENDING state. Host-initiated OUT cancellation additionally preserves the hardware DATA0/DATA1 toggle and drains queued completion events before rearming. IN cancellation retires the undrained transfer when the next command arrives, avoiding the DWC2 wait for IN tokens after the host stopped issuing them. These compatibility paths require physical tests for cancellation and disconnect, in addition to ordinary copying. See `docs/usb-cancel-fix.md` for the 12-case same-session cancellation test.

The object table has 1024 entries. Exceeding it returns an MTP error rather than silently omitting entries. The original full flash backup and the last verified application before MTP remain in `backups/`.

The local integration also corrects the GetObjectHandles/GetNumObjects root selector (0 = whole tree, UINT32_MAX = root children), emits correctly framed USB ObjectAdded/ObjectRemoved/ObjectInfoChanged events for committed web changes, and serves discovery/property metadata from the object cache. Directory scans release SD once their RAM response is built. Actual file transfers retain exclusive ownership until close/reset or an explicit idle web handoff. Windows hardware coverage is in `tests/mtp_check.cpp` and `docs/hardware-usb-copy.json`.
