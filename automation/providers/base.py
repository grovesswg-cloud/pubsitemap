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
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class EditorialReviewResult:
    result: str             # "PASS" | "FAIL"
    confidence: float       # 0.0 – 1.0
    revised_body: str | None = None   # optional surgical rewrite
    notes: list[str] = field(default_factory=list)


class FactVerificationProvider(ABC):
    @abstractmethod
    def verify(self, article_data: dict) -> FactVerificationResult:
        """Verify factual claims in article data against external sources."""
        ...


class VisionVerificationProvider(ABC):
    @abstractmethod
    def verify_image(self, image_url: str, article_data: dict) -> VisionVerificationResult:
        """Verify image shows the correct person in the correct context."""
        ...


class EditorialReviewProvider(ABC):
    @abstractmethod
    def review(self, article_data: dict) -> EditorialReviewResult:
        """Review article for voice, structure, and editorial standards."""
        ...
