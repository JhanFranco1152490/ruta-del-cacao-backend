class DuplicateDocumentError(ValueError):
    pass


class ProducerValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("Producer data is invalid.")
