import json
import logging


class JSONFormatter(logging.Formatter):
    def format(self, record):
        # Deliberately omit arbitrary record arguments, headers, bodies and exception strings.
        return json.dumps(
            {
                "level": record.levelname,
                "logger": record.name,
                "event": record.msg if isinstance(record.msg, str) else "application_event",
                "actor": getattr(record, "actor", None),
            }
        )


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger = logging.getLogger("atlasops")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
