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