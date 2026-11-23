"""Read-only overview of the mosaic-X5, from the latest SBF blocks (firmware guide §4)."""
import struct
from diagnostics import decode

BLOCKS = {5902: "ReceiverSetup", 4014: "ReceiverStatus", 5906: "PosCovGeodetic",
          5914: "ReceiverTime", 4013: "ChannelStatus", 4082: "QualityInd",
          4053: "NTRIPClientStatus", 4122: "NTRIPServerStatus", 4058: "IPStatus",
          4091: "OutputLink", 4059: "DiskStatus", 4092: "RFStatus", 4245: "GALAuthStatus"}
REQUEST = "exeSBFOnce,USB2," + "+".join(name for name in BLOCKS.values() if name != "ReceiverStatus")
SYSTEMS = {"GPS": [(1, 37)], "GLONASS": [(38, 68)], "Galileo": [(71, 106)],
           "SBAS": [(120, 140), (198, 215)], "BeiDou": [(141, 180), (223, 245)],
           "QZSS": [(181, 190)], "NavIC": [(191, 197), (216, 222)]}


def nested_rows(raw, child_count_at, parent_min, child_min):
    count, parent_size, child_size = raw[14:17]
    if count and parent_size < parent_min:
        raise ValueError("Invalid SBF parent length")
    pos = 20
    for _ in range(count):
        parent = raw[pos:pos + parent_size]
        n = parent[child_count_at]
        pos += parent_size
        end = pos + n * child_size
        if len(parent) != parent_size or end > len(raw) or (n and child_size < child_min):
            raise ValueError("Invalid SBF sub-block length")
        children = [raw[i:i + child_size] for i in range(pos, end, child_size)] if n else []
        yield parent, children
        pos = end


def constellations(raw):
    used = {s: set() for s in SYSTEMS}
    tracked = {s: set() for s in SYSTEMS}
    for parent, states in nested_rows(raw, 9, 12, 8):
        svid = parent[0] or struct.unpack_from("<H", parent, 2)[0]
        system = next((s for s, ranges in SYSTEMS.items() if any(a <= svid <= b for a, b in ranges)), None)
        if system is None:
            continue
        # GLONASS ID 62 has no known slot. The receiver channel distinguishes such satellites.
        key = (svid, parent[10] if svid == 62 else 0)
        for state in states:
            if state[0] != 0:
                continue
            tracking, position = struct.unpack_from("<HH", state, 2)
            if any((tracking >> shift) & 3 == 3 for shift in range(0, 16, 2)):
                tracked[system].add(key)
            if any((position >> shift) & 3 == 2 for shift in range(0, 16, 2)):
                used[system].add(key)
    return {s: {"used": len(used[s]), "tracked": len(tracked[s])} for s in SYSTEMS}


def output_links(raw):
    result = []
    for parent, types in nested_rows(raw, 1, 12, 2):
        result.append(dict(port=parent[0], sent=struct.unpack_from("<I", parent, 8)[0],
                           types=[t[0] for t in types if t[0]]))
    return result


def overview_data(frames, now):
    result = {}
    for block_id, (_, raw, stamp) in frames.items():
        name = BLOCKS[block_id]
        if name != "ReceiverSetup" and not 0 <= now - stamp <= 15000:
            continue
        try:
            if name == "ChannelStatus":
                data = constellations(raw)
            elif name == "OutputLink":
                data = output_links(raw)
            elif name == "IPStatus":
                if len(raw) < 36:
                    continue
                address = raw[32:36]
                data = {"ipv4": ".".join(str(b) for b in address) if any(address) else None}
            else:
                data = decode(raw)["fields"]
                if not data:
                    continue
        except (ValueError, IndexError, struct.error):
            continue
        result[name] = {"data": data, "t_ms": stamp}
    return result
