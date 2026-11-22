"""CloudNova cleaning pipeline (Session A).

Transforms data/raw/cloudnova_invoices.csv into the clean DuckDB-ready table
described by specs/cleaning_spec.md. See clean.run().
"""
from .clean import run  # noqa: F401
