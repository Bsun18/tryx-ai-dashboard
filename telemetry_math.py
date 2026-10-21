"""Pure calculations shared by collection and hardware-independent tests."""
import math
import re


def pcie_peak_mb_s(generation, width):
    """Single-direction lane capacity after encoding, before protocol overhead."""
    lane_rates = {1: 250.0, 2: 500.0, 3: 8000 * 128 / 130 / 8,
                  4: 16000 * 128 / 130 / 8, 5: 32000 * 128 / 130 / 8}
    return lane_rates[generation] * width if generation in lane_rates and width and width > 0 else None


def counter_rate(current, previous, name, field, elapsed):
    if name not in current or name not in previous or not math.isfinite(elapsed) or elapsed <= 0:
        return None
    delta = getattr(current[name], field) - getattr(previous[name], field)
    return delta / elapsed / 1e6 if delta >= 0 else None


def short_label(value, limit=26):
    value = re.sub(r'\(R\)|\(TM\)|®|™', '', str(value or ''), flags=re.I)
    value = re.sub(r'\s+\d+-Core Processor\s*$', '', value, flags=re.I)
    value = re.sub(r'^NVIDIA\s+GeForce\s+|^AMD\s+(?=Ryzen)', '', value, flags=re.I)
    value = ' '.join(value.split())
    return value if len(value) <= limit else value[:limit-1] + '…'


def select_disk(disks, requested_index=None):
    if requested_index is not None:
        return next((d for d in disks if d['index'] == requested_index), None)
    internal = [d for d in disks if str(d.get('bus', '')).upper() not in {'USB', 'SD', 'MMC', 'ISCSI', 'VIRTUAL', 'FILE BACKED VIRTUAL'}]
    return min(internal, key=lambda d: (str(d.get('bus', '')).upper() != 'NVME',
                                       not d.get('system', False), d['index'])) if internal else None


def storage_limits(disk, config):
    if not disk:
        return None, None, 'UNKNOWN'
    read = config.get('storage_read_peak_mb_s')
    write = config.get('storage_write_peak_mb_s')
    if read is not None or write is not None:
        return read, write, 'REF'
    peak = pcie_peak_mb_s(disk.get('max_gen'), disk.get('max_width')) if str(disk.get('bus', '')).upper() == 'NVME' else None
    return peak, peak, 'LINK' if peak is not None else 'UNKNOWN'
