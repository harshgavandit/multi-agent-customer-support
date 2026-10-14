"""Messages safe to show in the UI; never expose raw provider exceptions."""


class SupportError(RuntimeError):
    pass


class RateLimitExceeded(SupportError):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Request limit reached. Please try again in {retry_after_seconds} seconds.")


class RateLimitUnavailable(SupportError):
    def __init__(self):
        super().__init__("Rate limiting is temporarily unavailable. Please try again later or check the Redis configuration.")


class ModelUnavailable(SupportError):
    pass
