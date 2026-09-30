"""Backward-compatible AI imports. Use payment_python_tests.ai.assistant."""

from payment_python_tests.ai.assistant import (
    AiAssistant,
    analyze_failure,
    analyze_failure_with_ai,
    generate_contract_draft,
    review_contract_with_ai,
    save_contract_draft,
)

__all__ = [
    "AiAssistant",
    "analyze_failure",
    "analyze_failure_with_ai",
    "generate_contract_draft",
    "review_contract_with_ai",
    "save_contract_draft",
]
