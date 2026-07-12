"""Checks for the external tools/kernel features DataPulse depends on.

Read-only and safe to call as a normal user (used by both the root collector
and the unprivileged viewer/tray) so missing prerequisites show up as a clear
message instead of the app silently doing nothing.
"""
import shutil


def _net_cls_available():
    try:
        with open("/proc/cgroups") as f:
            for line in f:
                fields = line.split()
                if fields and fields[0] == "net_cls":
                    return len(fields) >= 4 and fields[3] == "1"
    except OSError:
        pass
    return False


def check_prerequisites():
    """Return a list of (name, ok, detail) tuples."""
    checks = [
        ("nethogs", shutil.which("nethogs") is not None,
         "Required for per-app bandwidth monitoring. Install with: sudo apt install nethogs"),
        ("iptables", shutil.which("iptables") is not None,
         "Required for the block/kill-switch features. Install with: sudo apt install iptables"),
        ("tc (iproute2)", shutil.which("tc") is not None,
         "Required for the upload-limit feature. Install with: sudo apt install iproute2"),
        ("pkexec", shutil.which("pkexec") is not None,
         "Required to apply block/limit changes as root from the GUI. "
         "Install with: sudo apt install policykit-1"),
        ("net_cls cgroup controller", _net_cls_available(),
         "Required for per-app block/limit enforcement. Usually built into the kernel; "
         "if disabled, monitoring still works but block/limit/kill-switch will fail."),
    ]
    return checks


def missing_prerequisites():
    return [(name, detail) for name, ok, detail in check_prerequisites() if not ok]
