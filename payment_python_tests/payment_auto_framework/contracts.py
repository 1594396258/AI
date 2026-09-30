"""Backward-compatible imports. Use config.contract_loader and models instead."""

from payment_python_tests.config.contract_loader import load_contract
from payment_python_tests.models.channel_contract import ChannelContract

__all__ = ["ChannelContract", "load_contract"]
