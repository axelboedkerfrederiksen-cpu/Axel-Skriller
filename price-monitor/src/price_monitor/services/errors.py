class ServiceError(RuntimeError):
    """Base exception for expected application-service failures."""


class NotFoundError(ServiceError):
    pass


class ConflictError(ServiceError):
    pass


class InvalidRequestError(ServiceError):
    pass


class LeaseLostError(ConflictError):
    pass
