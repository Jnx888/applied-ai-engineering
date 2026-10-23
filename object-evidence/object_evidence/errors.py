class EvidenceError(Exception):
    """A safe, fixed error code. Never include object contents or SDK messages."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
