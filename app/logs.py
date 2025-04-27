from datetime import datetime
import logging
import os
import sys
from queue import Queue
from logging.handlers import QueueHandler, RotatingFileHandler
from rich.logging import RichHandler
from rich.console import Console
import functools

console = Console()

log_queue = Queue(-1)  # Unlimited size

LOGGING_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(filename)s:%(lineno)d | %(message)s"

# Setup logging configuration
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"arbitrage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# Create formatters and handlers
formatter = logging.Formatter(LOGGING_FORMAT)

# File handler with rotation (10 files of 5MB each)
f_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=10)
f_handler.setFormatter(formatter)
f_handler.setLevel(logging.DEBUG)

# Console handler with rich formatting
s_handler = RichHandler(console=console)
s_handler.setLevel(logging.INFO)

queue_handler = QueueHandler(log_queue)
queue_handler.setLevel(0)

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG,
    format=LOGGING_FORMAT,
    handlers=[queue_handler, s_handler, f_handler]
)

# Add custom log levels
logging.addLevelName(25, "SUCCESS")
logging.addLevelName(5, "TRACE")

def success(self, message, *args, **kwargs):
    """Log 'msg % args' with severity 'SUCCESS'."""
    self.log(25, message, *args, **kwargs)

def trace(self, message, *args, **kwargs):
    """Log 'msg % args' with severity 'TRACE'."""
    self.log(5, message, *args, **kwargs)

# Add the custom methods to the Logger class
logging.Logger.success = success
logging.Logger.trace = trace

# Get the main logger
logger = logging.getLogger(__name__)

# Setup exception hook to log uncaught exceptions
def log_uncaught_exceptions(exc_type, exc_value, exc_traceback):
    """Handler for uncaught exceptions that will log them"""
    if issubclass(exc_type, KeyboardInterrupt):
        # Call the default handler for KeyboardInterrupt
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = log_uncaught_exceptions

# Decorator for logging function entry/exit
def log_function(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        module_logger = logging.getLogger(func.__module__)
        module_logger.debug(f"Entering {func.__name__}")
        try:
            result = func(*args, **kwargs)
            module_logger.debug(f"Exiting {func.__name__}")
            return result
        except Exception as e:
            module_logger.error(f"Exception in {func.__name__}: {e}", exc_info=True)
            raise
    return wrapper

logger.info(f"Starting arbitrage odds system. Logs will be saved to {log_file}")