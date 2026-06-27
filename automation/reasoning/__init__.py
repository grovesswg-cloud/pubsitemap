"""Groves Engine — Editorial Intelligence Engine.

The engine separates editorial reasoning from prose generation.
By the time the writer is invoked, all critical decisions are already made.

Stages (in order):
  research     — publication memory + editorial positioning (stubs; enriched in PR-006.5/006.6)
  observation  — structured observations + interpretations
  thesis       — synthesis + perspective + thesis candidates + challenge + selection + counterargument
  outline      — evidence mapping + paragraph outline + editor notes

The writer receives a ReasoningBrief and renders it into prose.
The engine is publication-agnostic: editorial context and articles index are
passed in by the caller, not imported here.
"""
from reasoning.brief import ReasoningBrief, EvidenceItem
from reasoning.engine import run

__all__ = ['ReasoningBrief', 'EvidenceItem', 'run']
