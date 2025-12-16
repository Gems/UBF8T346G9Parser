import logging

_log_level = logging.INFO


def set_log_level(level):
    global _log_level
    _log_level = level


class Logger:
    """Universal logger"""

    @property
    def logger(self):
        # Configure root logger once; subsequent calls keep existing handlers.
        if not logging.getLogger().handlers:
            logging.basicConfig(
                format='[%(asctime)s] %(levelname)s - %(message)s',
                datefmt='%d-%m-%Y %H:%M:%S',
                level=_log_level,
            )
        logger = logging.getLogger(__name__)
        logger.setLevel(_log_level)
        return logger
