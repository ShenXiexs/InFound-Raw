from .outreach_filter_br import BR_OUTREACH_FILTER_SCRIPT
from .outreach_filter_base import OutreachFilterScript
from .outreach_filter_fr import FR_OUTREACH_FILTER_SCRIPT
from .outreach_filter_id import ID_OUTREACH_FILTER_SCRIPT
from .outreach_filter_mx import MX_OUTREACH_FILTER_SCRIPT
from .outreach_filter_vn import VN_OUTREACH_FILTER_SCRIPT

OUTREACH_FILTER_SCRIPTS = {
    "BR": BR_OUTREACH_FILTER_SCRIPT,
    "FR": FR_OUTREACH_FILTER_SCRIPT,
    "ID": ID_OUTREACH_FILTER_SCRIPT,
    "MX": MX_OUTREACH_FILTER_SCRIPT,
    "VN": VN_OUTREACH_FILTER_SCRIPT,
}


def get_outreach_filter_script(region: str) -> OutreachFilterScript:
    region_code = str(region or "").upper()
    return OUTREACH_FILTER_SCRIPTS.get(region_code, MX_OUTREACH_FILTER_SCRIPT)


def has_outreach_filter_script(region: str) -> bool:
    return str(region or "").upper() in OUTREACH_FILTER_SCRIPTS


__all__ = [
    "BR_OUTREACH_FILTER_SCRIPT",
    "FR_OUTREACH_FILTER_SCRIPT",
    "OutreachFilterScript",
    "ID_OUTREACH_FILTER_SCRIPT",
    "MX_OUTREACH_FILTER_SCRIPT",
    "VN_OUTREACH_FILTER_SCRIPT",
    "OUTREACH_FILTER_SCRIPTS",
    "get_outreach_filter_script",
    "has_outreach_filter_script",
]
