from datetime import datetime
import logging
import os
from queue import Queue
from logging.handlers import QueueHandler
from rich.logging import RichHandler
from rich.console import Console

console = Console()

# Queue pour stocker les logs
class NeverfullQueue(Queue):
    def __init__(self, *args,**kwargs):
        super().__init__(*args,**kwargs)
    
    def put_nowait(self, item):
        try:
            super().put_nowait(item)
        except:
            try:
                super().get_nowait()  # Remove oldest item if queue is full
                super().put_nowait(item)
            except:
                pass  # If queue is empty or other error occurs, just skip

log_queue = NeverfullQueue(maxsize=1000)  # Garder les 1000 derniers logs

LOGGING_FORMAT = "%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s"

# Setup logging configuration
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"arbitrage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# Create formatters and handlers
formatter = logging.Formatter(LOGGING_FORMAT)

f_handler = logging.FileHandler(log_file)
f_handler.setFormatter(formatter)
f_handler.setLevel(logging.DEBUG)

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
logging.addLevelName(25, "success")
logging.addLevelName(5, "trace")

logger = logging.getLogger(__name__)

logger.info(f"Starting arbitrage odds system. Logs will be saved to {log_file}")