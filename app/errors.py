class AppError(Exception):
    """Base class for the error categories from the spec (section 25)."""


class ConfigurationError(AppError):
    pass


class AuthenticationError(AppError):
    pass


class RedditApiError(AppError):
    pass


class RateLimitError(AppError):
    pass


class ParsingError(AppError):
    pass


class LLMError(AppError):
    pass


class ValidationError(AppError):
    pass


class PublishError(AppError):
    pass
