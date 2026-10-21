"""Explicit application capabilities; no dynamic imports from tenant input."""

from minkops_platform.accounts.handlers import BillHandler, DiscoveryHandler

from .proposal import ProposalHandler

# Extensions register an ordinary tested Python handler here. The lifecycle
# never needs another branch for a new workflow key or customer identity.
HANDLERS = {
    "accounts.discovery": DiscoveryHandler(),
    "accounts.bill": BillHandler(),
    "skill.proposal": ProposalHandler(),
}
