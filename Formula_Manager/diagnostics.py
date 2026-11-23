"""Inspect SBF blocks on demand, off the serial read path."""
import math
import re
import struct
from collections import OrderedDict

from pysbf2 import SBFReader
from pysbf2.sbftypes_core import SBF_MSGIDS

# These get commands return operational receiver settings, without account credentials.
GROUPS = {
    "Poloha a anténa": "PVTMode ReceiverDynamics ElevationMask CN0Mask AntennaOffset AntennaLocation StaticPosGeodetic StaticPosCartesian SmoothingInterval GeodeticDatum GeoidUndulation RAIMLevels",
    "Družice a signál": "SatelliteTracking SignalTracking SatelliteUsage SignalUsage ChannelAllocation AGCMode MultipathMitigation WBIMitigation NotchFiltering TrackingLoopParameters SatelliteHealthOverride SignalHealthOverride",
    "Korekce": "DiffCorrUsage DiffCorrMaxAge NetworkRTKConfig SBASCorrections IonosphereModel TroposphereModel RTCMv3Usage RTCMv3Formatting RTCMv3Output RTCMv3Interval RTCMv3Delay",
    "Porty a výstupy": "DataInOut SBFOutput SBFGroups NMEAOutput NMEAVersion NMEAPrecision NMEATalkerID COMSettings USBInternetAccess IPSettings IPPortSettings IPServerSettings",
    "Přijímač a čas": "ReceiverCapabilities ReceiverInterface PowerMode TimingSystem ClockSyncThreshold PPSParameters EventParameters TimeSyncSource RINEXLogging",
}
PARAMETERS = {p: group for group, params in GROUPS.items() for p in params.split()}
EDITABLE = set(("ElevationMask CN0Mask ReceiverDynamics PVTMode SatelliteTracking SignalTracking "
                "SatelliteUsage SignalUsage AGCMode MultipathMitigation SmoothingInterval DiffCorrUsage "
                "DiffCorrMaxAge SBASCorrections IonosphereModel TroposphereModel RAIMLevels").split())
SNAPSHOT = "exeSBFOnce,USB2,ReceiverSetup+DOP+SatVisibility+ChannelStatus+RFStatus+QualityInd+InputLink+ReceiverTime"


def change_command(name, arguments):
    if name not in EDITABLE or not isinstance(arguments, str) or not re.fullmatch(
            r"[a-zA-Z0-9+.,_ -]{1,200}", arguments) or not arguments.strip(" ,"):
        raise ValueError("Neplatný parametr nebo argumenty příkazu.")
    return "set" + name + "," + arguments.strip()


def clean_reply(reply):
    return "\n".join(line.strip() for line in reply.splitlines()
                     if line.strip() and not line.lstrip().startswith(("$R", "$--", "---->", "USB1>")))


def decode(raw):
    # Preserve the original bytes even for an undocumented block or an unsupported revision.
    fields = {}
    try:
        if (int.from_bytes(raw[4:6], "little") & 8191) == 5902:
            # pysbf2 1.0.7 omits RxSerialNumber and shifts subsequent ReceiverSetup fields.
            layout = (("TOW","I"), ("WNc","H"), ("Reserved","H"), ("MarkerName","60s"),
                      ("MarkerNumber","20s"), ("Observer","20s"), ("Agency","40s"),
                      ("RxSerialNumber","20s"), ("RxName","20s"), ("RxVersion","20s"),
                      ("AntSerialNbr","20s"), ("AntType","20s"), ("deltaH","f"), ("deltaE","f"),
                      ("deltaN","f"), ("MarkerType","20s"), ("GNSSFWVersion","40s"),
                      ("ProductName","40s"), ("Latitude","d"), ("Longitude","d"), ("Height","f"),
                      ("StationCode","10s"), ("MonumentIdx","B"), ("ReceiverIdx","B"), ("CountryCode","3s"))
            offset = 8
            for key, fmt in layout:
                size = struct.calcsize("<" + fmt)
                if offset + size > len(raw):
                    break
                val = struct.unpack_from("<" + fmt, raw, offset)[0]
                if isinstance(val, bytes):
                    val = val.partition(b"\0")[0].decode("ascii", errors="replace")
                elif isinstance(val, float) and not math.isfinite(val):
                    val = None
                fields[key] = val
                offset += size
            return {"hex": raw.hex(" "), "fields": fields}
        msg = SBFReader.parse(raw)
        for key, val in vars(msg).items():
            if key.startswith("_"):
                continue
            if isinstance(val, bytes):
                val = val.hex(" ")
            elif isinstance(val, float) and not math.isfinite(val):
                val = None
            fields[key] = val
    except Exception as exc:
        return {"hex": raw.hex(" "), "fields": {}, "error": str(exc)[:200]}
    return {"hex": raw.hex(" "), "fields": fields}


class BlockCache:
    def __init__(self):
        self.latest = OrderedDict()

    def observe(self, block_id, raw, timestamp):
        prior = self.latest.pop(block_id, None)
        self.latest[block_id] = ((prior[0] if prior else 0) + 1, raw, timestamp)
        if len(self.latest) > 256:
            self.latest.popitem(last=False)

    def snapshot(self, selected):
        rows = []
        detail = None
        for block_id, (count, raw, timestamp) in self.latest.items():
            name = SBF_MSGIDS.get(block_id, ("SBF " + str(block_id),))[0]
            row = dict(id=block_id, name=name, count=count, t_ms=timestamp,
                       length=len(raw), revision=raw[5] >> 5)
            rows.append(row)
            if block_id == selected:
                detail = (row, raw)
        return sorted(rows, key=lambda r: r["name"]), detail

