import re


_LEADING_FLAG = re.compile(r"^[\U0001F1E6-\U0001F1FF]{2}\s*")


def display_organization_name(name: str | None, ransomware_group: str | None) -> str | None:
    """Hide source-decorative flag emoji when a separate country flag is shown."""
    if name and (ransomware_group or "").casefold() == "kazu":
        return _LEADING_FLAG.sub("", name)
    return name
