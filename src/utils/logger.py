import logging

def setup_logger(name: str = "qdarchive") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    h = logging.StreamHandler()
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    h.setFormatter(fmt)
    logger.addHandler(h)
    return logger