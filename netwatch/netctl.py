"""Per-app network blocking and upload bandwidth limiting.

Enforcement mechanism: processes matching a controlled app's binary name are
classified into a net_cls cgroup (one per app, stable classid). iptables
drops outbound packets tagged with a blocked app's classid; tc (htb) shapes
upload for a rate-limited app's classid.

Note: only upload can be rate-limited this way. Ingress packets arrive
before the kernel can associate them with a local process/cgroup, so
per-app *download* throttling isn't achievable through cgroup classification
-- only blocking (which stops both directions, since no request means no
response) and upload shaping are implemented.

All functions in this module require root. Must run as root (systemd
service, or invoked via pkexec from the GUI).
"""
import json
import os
import re
import subprocess

CGROUP_ROOT = "/sys/fs/cgroup/net_cls/linuxnetwatch"
RULES_PATH = "/var/lib/linuxnetwatch/rules.json"
IPTABLES_CHAIN = "LINUXNETWATCH_BLOCK"
TC_MAJOR = 1
TC_DEFAULT_MINOR = 999  # class for unclassified/default traffic
TC_ROOT_RATE = "1000mbit"  # ceiling for the root class; effectively "no limit"
MIN_CLASSID_MINOR = 10


class NetCtlError(RuntimeError):
    pass


def _run(cmd, check=True):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise NetCtlError(f"command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
    return result


def load_rules():
    if not os.path.exists(RULES_PATH):
        return {}
    with open(RULES_PATH) as f:
        return json.load(f)


def save_rules(rules):
    os.makedirs(os.path.dirname(RULES_PATH), exist_ok=True)
    with open(RULES_PATH, "w") as f:
        json.dump(rules, f, indent=2)
    os.chmod(RULES_PATH, 0o644)


def ensure_net_cls_mounted():
    if os.path.isdir(CGROUP_ROOT):
        return
    os.makedirs("/sys/fs/cgroup/net_cls", exist_ok=True)
    if not os.path.ismount("/sys/fs/cgroup/net_cls"):
        _run(["mount", "-t", "cgroup", "-o", "net_cls", "net_cls", "/sys/fs/cgroup/net_cls"])
    os.makedirs(CGROUP_ROOT, exist_ok=True)


def default_interface():
    result = _run(["ip", "route", "show", "default"], check=False)
    match = re.search(r"dev (\S+)", result.stdout)
    if not match:
        raise NetCtlError("could not determine default network interface")
    return match.group(1)


def _next_minor(rules):
    used = {entry["minor"] for entry in rules.values()}
    minor = MIN_CLASSID_MINOR
    while minor in used or minor == TC_DEFAULT_MINOR:
        minor += 1
    return minor


def _classid_hex(minor):
    return f"0x{TC_MAJOR:04x}{minor:04x}"


def get_or_create_entry(app_name, rules):
    entry = rules.get(app_name)
    if entry is None:
        entry = {"minor": _next_minor(rules), "blocked": False, "limit_kbps": None,
                  "daily_cap_mb": None}
        rules[app_name] = entry
        ensure_net_cls_mounted()
        cg_dir = f"{CGROUP_ROOT}/{app_name}"
        os.makedirs(cg_dir, exist_ok=True)
        with open(f"{cg_dir}/net_cls.classid", "w") as f:
            f.write(_classid_hex(entry["minor"]))
    return entry


def classify_running_processes(rules):
    """Move any running process whose binary name matches a controlled app
    into that app's cgroup. Cheap to call repeatedly (writing an already
    member pid is a no-op)."""
    if not rules:
        return
    by_name = {name: entry for name, entry in rules.items()}
    for pid_str in os.listdir("/proc"):
        if not pid_str.isdigit():
            continue
        comm_path = f"/proc/{pid_str}/comm"
        try:
            with open(comm_path) as f:
                comm = f.read().strip()
        except OSError:
            continue
        entry = by_name.get(comm)
        if entry is None:
            continue
        procs_path = f"{CGROUP_ROOT}/{comm}/cgroup.procs"
        try:
            with open(procs_path, "w") as f:
                f.write(pid_str)
        except OSError:
            pass


def _ensure_iptables_chain():
    result = _run(["iptables", "-t", "filter", "-C", "OUTPUT", "-j", IPTABLES_CHAIN], check=False)
    if result.returncode == 0:
        return
    _run(["iptables", "-N", IPTABLES_CHAIN], check=False)
    _run(["iptables", "-A", "OUTPUT", "-j", IPTABLES_CHAIN])


def set_blocked(app_name, blocked):
    rules = load_rules()
    entry = get_or_create_entry(app_name, rules)
    entry["blocked"] = blocked
    save_rules(rules)

    _ensure_iptables_chain()
    classid = _classid_hex(entry["minor"])
    _run(["iptables", "-D", IPTABLES_CHAIN, "-m", "cgroup", "--cgroup", classid, "-j", "DROP"],
         check=False)
    if blocked:
        _run(["iptables", "-A", IPTABLES_CHAIN, "-m", "cgroup", "--cgroup", classid, "-j", "DROP"])
    classify_running_processes(rules)


def _ensure_tc_root(iface):
    result = _run(["tc", "qdisc", "show", "dev", iface], check=False)
    if f"htb {TC_MAJOR}:" in result.stdout:
        return
    _run(["tc", "qdisc", "add", "dev", iface, "root", "handle", f"{TC_MAJOR}:",
          "htb", "default", str(TC_DEFAULT_MINOR)])
    _run(["tc", "class", "add", "dev", iface, "parent", f"{TC_MAJOR}:", "classid",
          f"{TC_MAJOR}:1", "htb", "rate", TC_ROOT_RATE])
    _run(["tc", "class", "add", "dev", iface, "parent", f"{TC_MAJOR}:1", "classid",
          f"{TC_MAJOR}:{TC_DEFAULT_MINOR}", "htb", "rate", TC_ROOT_RATE, "ceil", TC_ROOT_RATE])
    _run(["tc", "filter", "add", "dev", iface, "parent", f"{TC_MAJOR}:", "protocol", "ip",
          "prio", "1", "handle", "1:", "cgroup"])


def set_limit(app_name, kbps):
    """Set (or clear, if kbps is None) an upload rate limit in kbit/s."""
    rules = load_rules()
    entry = get_or_create_entry(app_name, rules)
    entry["limit_kbps"] = kbps
    save_rules(rules)

    iface = default_interface()
    _ensure_tc_root(iface)
    classid = f"{TC_MAJOR}:{entry['minor']}"
    _run(["tc", "class", "del", "dev", iface, "classid", classid], check=False)
    if kbps:
        _run(["tc", "class", "add", "dev", iface, "parent", f"{TC_MAJOR}:1", "classid",
              classid, "htb", "rate", f"{kbps}kbit", "ceil", f"{kbps}kbit"])
    classify_running_processes(rules)


def set_daily_cap(app_name, cap_mb):
    rules = load_rules()
    get_or_create_entry(app_name, rules)
    rules[app_name]["daily_cap_mb"] = cap_mb
    save_rules(rules)


def apply_all_rules():
    """Re-apply every stored rule; call on collector startup so rules survive
    a reboot/service restart (cgroups and iptables/tc state don't persist)."""
    rules = load_rules()
    ensure_net_cls_mounted()
    for app_name, entry in rules.items():
        cg_dir = f"{CGROUP_ROOT}/{app_name}"
        os.makedirs(cg_dir, exist_ok=True)
        with open(f"{cg_dir}/net_cls.classid", "w") as f:
            f.write(_classid_hex(entry["minor"]))
        if entry.get("blocked"):
            set_blocked(app_name, True)
        if entry.get("limit_kbps"):
            set_limit(app_name, entry["limit_kbps"])
    classify_running_processes(rules)
