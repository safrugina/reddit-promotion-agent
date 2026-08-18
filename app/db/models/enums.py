import enum


class ProjectStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class FactType(enum.StrEnum):
    FEATURE = "feature"
    CLAIM = "claim"
    METRIC = "metric"
    USE_CASE = "use_case"
    AUDIENCE = "audience"
    LIMITATION = "limitation"
    TECHNICAL_DETAIL = "technical_detail"
    LINK = "link"
    PROBLEM = "problem"
    DIFFERENTIATOR = "differentiator"


class OpportunityStatus(enum.StrEnum):
    NEW = "NEW"
    ANALYZING = "ANALYZING"
    READY = "READY"
    REJECTED = "REJECTED"
    USED = "USED"
    EXPIRED = "EXPIRED"


class ContentType(enum.StrEnum):
    POST = "POST"
    COMMENT = "COMMENT"


class ContentAngle(enum.StrEnum):
    EDUCATIONAL = "EDUCATIONAL"
    TECHNICAL = "TECHNICAL"
    PROBLEM_SOLUTION = "PROBLEM_SOLUTION"
    CASE_STUDY = "CASE_STUDY"
    OPEN_SOURCE = "OPEN_SOURCE"
    QUESTION = "QUESTION"
    DISCUSSION = "DISCUSSION"
    DATA = "DATA"
    EXPERIMENT = "EXPERIMENT"
    ANNOUNCEMENT = "ANNOUNCEMENT"


class ApprovalStatus(enum.StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EDITED = "EDITED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class ValidationStatus(enum.StrEnum):
    PASS = "PASS"
    REGENERATE = "REGENERATE"
    BLOCK = "BLOCK"
    PENDING = "PENDING"
