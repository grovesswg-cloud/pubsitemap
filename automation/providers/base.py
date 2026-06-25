"""LORD Quality Pipeline — Provider Abstract Base Classes

All AI service calls go through these interfaces. Concrete implementations
live in providers/impl/. The Editorial Board never references a specific
model or vendor directly — only these interfaces.

To swap a provider (e.g. Gemini → Perplexity for fact verification):
  Edit one file in providers/impl/. Nothing else changes.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class VerificationSource:
    """A single source used to verify a factual claim."""
    name: str
    url: str = ''
    claim: str = ''   # which entity or claim this source confirmed


@dataclass
class FactVerificationResult:
    result: str                             # "PASS" | "FAIL" | "UNCERTAIN"
    confidence: float                       # 0.0 – 1.0
    sources: list[VerificationSource] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class VisionVerificationResult:
    result: str             # "PASS" | "FAIL" | "UNCERTAIN"
    confidence: float       # 0.0 – 1.0
    person_match: bool = False
    context_match: bool = False
    technical_pass: bool = False
    editorial_quality: str = ''   # "strong" | "adequate" | "weak"
    editorial_note: str = ''
    entity_match: bool = True         # False → FAIL (identity mismatch, not just name match)
    expected_entity: str = ''         # e.g. "Camille (French singer, born 1978)"
    detected_entity: str = ''         # e.g. "Camille Claudel (French sculptor, 1864–1943)"
    entity_confidence: float = 0.0    # 0.0 – 1.0
    mismatch_reason: str = ''         # human-readable explanation when entity_match=False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class EditorialStandard:
    """Publication-specific editorial configuration.

    Passed to EditorialReviewProvider so the same provider implementation
    can evaluate different publications without modification.

    Example usage:
        lord_standard = EditorialStandard(
            publication_name='LORD',
            voice_prompt=LORD_VOICE,
        )
        provider = ClaudeEditorialProvider(api_key=..., model=..., editorial_standard=lord_standard)
    """
    publication_name: str    # e.g. "LORD"
    voice_prompt: str        # full voice/tone description injected into the review prompt


@dataclass
class EditorialIssue:
    severity: str       # "FAIL" | "WARN" | "INFO"
    category: str       # e.g. "clarity" | "structure" | "tone" | "pacing" | "repetition" ...
    description: str    # what the issue is
    quote: str = ''     # offending text excerpt (optional)


@dataclass
class EditorialReviewResult:
    result: str             # "PASS" | "FAIL" | "UNCERTAIN"
    confidence: float       # 0.0 – 1.0
    summary: str = ''
    issues: list[EditorialIssue] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    revised_body: str | None = None   # reserved for future surgical rewrite workflow


@dataclass
class SearchReadinessIssue:
    severity: str        # "FAIL" | "WARN" | "INFO"
    category: str        # "title" | "meta_description" | "duplicate_metadata" | "headings" |
                         # "open_graph" | "image_metadata" | "structured_data" | "slug" |
                         # "internal_links" | "accessibility"
    description: str
    recommendation: str = ''


@dataclass
class SearchReadinessResult:
    result: str          # "PASS" | "FAIL"
    issues: list[SearchReadinessIssue] = field(default_factory=list)
    summary: str = ''


class FactVerificationProvider(ABC):
    @abstractmethod
    def verify(self, article_data: dict) -> FactVerificationResult:
        """Verify factual claims in article data against external sources."""
        ...


class VisionVerificationProvider(ABC):
    @abstractmethod
    def verify_image(self, image_bytes: bytes, mime_type: str, article_data: dict) -> VisionVerificationResult:
        """Verify image shows the correct person in the correct context."""
        ...


class EditorialReviewProvider(ABC):
    @abstractmethod
    def review(self, article_data: dict) -> EditorialReviewResult:
        """Review article for voice, structure, and editorial standards.

        Returns EditorialReviewResult with structured issues classified by severity:
          FAIL — prevents publication (incoherent structure, absent conclusion, etc.)
          WARN — editorial weakness, allows publication with warning logged
          INFO — minor observation, no publication impact
        """
        ...


class SearchReadinessProvider(ABC):
    @abstractmethod
    def evaluate(self, article_data: dict) -> SearchReadinessResult:
        """Evaluate article for technical publication quality and search readiness.

        Philosophy: optimize for understanding, not manipulation. A technically
        excellent article naturally satisfies modern search requirements without
        keyword density hacks or algorithmic gaming.

        Returns SearchReadinessResult with structured issues classified by severity:
          FAIL — objective failure blocking publication (e.g. missing title)
          WARN — meaningful gap, allows publication with warning logged
          INFO — minor observation, no publication impact
        """
        ...
