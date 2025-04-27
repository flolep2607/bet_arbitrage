# Arbitrage Manager Configuration
ARBITRAGE_EXPIRATION_TIMER = 30 * 60  # 30 minutes in seconds
MAX_HISTORY_ENTRIES = 1000
MIN_PROFIT_THRESHOLD = 0.5  # Minimum profit % to consider

# Stats Manager Configuration
MAX_RECENT_ODDS = 1000  # Number of recent odds to keep for rate calculation
STATS_UPDATE_INTERVAL = 5.0  # How often to update stats display in seconds

# Fuzzy Matching Configuration
TEAM_NAME_MATCH_RATIO = 95  # Minimum ratio for fuzzy name matching
SIMILAR_STRINGS_THRESHOLD = 0.9  # Threshold for string similarity comparison

# Web Interface Configuration
WEBAPP_PORT = 8000
WEBSOCKET_RETRY_MAX = 3      # Maximum number of retry attempts for WebSocket connections
WEBSOCKET_RETRY_DELAY = 2    # Initial delay in seconds before retrying (will be multiplied by retry count)
WEBSOCKET_CONNECT_TIMEOUT = 10  # Timeout in seconds to wait for WebSocket connection

# API Configuration
API_REQUEST_TIMEOUT = 10     # Timeout in seconds for API requests
TOKEN_REFRESH_INTERVAL = 300 # Token refresh interval in seconds for Dexsport

# Rate Limiting
API_RATE_LIMIT = 5           # Maximum requests per second for API calls
WEBSOCKET_MESSAGE_RATE = 5   # Maximum messages per second for WebSocket