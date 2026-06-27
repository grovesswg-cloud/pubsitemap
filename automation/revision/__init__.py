"""Groves Engine — Editorial Revision Engine package.

The publication's internal editor: critiques a draft against its ReasoningBrief,
triages the highest-impact weaknesses, and rewrites only those sections.
"""
from revision.report import RevisionReport, CritiqueNote
from revision.engine import run

__all__ = ['RevisionReport', 'CritiqueNote', 'run']
