from collections import Counter
from typing import Iterable, Protocol

MASK = "••"
VISIBLE_DIGITS = 2


class _Account(Protocol):
    id: str
    type: str
    number: str


def account_label(
    account_type: str, number: str, hide: bool, visible: int = VISIBLE_DIGITS
) -> str:
    """'TFSA #12345', or 'TFSA ••45' when account numbers are hidden.

    A number no longer than `visible` is masked entirely.
    """
    if not hide:
        return f"{account_type} #{number}"
    tail = number[-visible:] if len(number) > visible else ""
    return f"{account_type} {MASK}{tail}"


def account_labels(accounts: Iterable[_Account], hide: bool) -> dict[str, str]:
    """Display label per account id, kept distinct when numbers are hidden.

    Labels double as chart grouping keys, so masked labels that collide show
    more trailing characters until they differ, then fall back to a counter.
    """
    accounts = list(accounts)
    labels = {a.id: account_label(a.type, a.number, hide) for a in accounts}
    if not hide:
        return labels

    longest = max((len(a.number) for a in accounts), default=0)
    for visible in range(VISIBLE_DIGITS + 1, longest):
        counts = Counter(labels.values())
        clashing = [a for a in accounts if counts[labels[a.id]] > 1]
        if not clashing:
            return labels
        for a in clashing:
            labels[a.id] = account_label(a.type, a.number, hide, visible)

    counts = Counter(labels.values())
    seen: Counter[str] = Counter()
    for a in accounts:
        label = labels[a.id]
        if counts[label] > 1:
            seen[label] += 1
            labels[a.id] = f"{label} ({seen[label]})"
    return labels
