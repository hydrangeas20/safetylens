"""Audit of the archived 2026 SafetyLens experiment (hydrangeas20/safetylens-research).

Nothing in this package modifies the archive. Raw model responses never leave it:
the redaction step keeps hashes, lengths and derived quality features only.
"""

ARCHIVE_REPO = "https://github.com/hydrangeas20/safetylens-research"
ARCHIVE_COMMIT = "b5d0dba906b2d6bbeb0bdfc0cbc958079e8ac3cc"

MODEL_FILES: dict[str, str] = {
    "Llama-3.1-8B": "results/safetylens_Llama-3.1-8B.csv",
    "Llama-3.3-70B": "results/safetylens_Llama-3.3-70B.csv",
    "Qwen3-32B": "results/safetylens_Qwen3-32B.csv",
}

ORIGINAL_OUTPUT_FILES: tuple[str, ...] = (
    "results/stats.csv",
    "results/refusal_rates.csv",
    "results/divergence_summary.csv",
)
