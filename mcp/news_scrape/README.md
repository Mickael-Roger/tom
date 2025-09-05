# News Scraping Extensions

This directory contains extensible news scrapers for the News MCP Server. Scrapers are automatically discovered and loaded at startup.

## Architecture

The news scraping system uses a plugin-based architecture where:

- **base_scraper.py**: Defines the `BaseScraper` abstract base class
- **__init__.py**: Provides automatic discovery and loading functions
- **Individual scrapers**: Implement specific scraping logic for different news sources

## Creating a New Scraper

To create a new scraper, follow these steps:

### 1. Create a new Python file

Create a new `.py` file in this directory (e.g., `example_scraper.py`).

### 2. Implement the BaseScraper interface

```python
"""
Example news scraper extension
"""

import requests
from typing import Dict, Any, List
from .base_scraper import BaseScraper


class ExampleScraper(BaseScraper):
    """Scraper for Example News Site"""
    
    @property
    def name(self) -> str:
        return "example"  # Unique identifier for this scraper
    
    @property
    def category(self) -> str:
        return "Tech"  # Default category for articles
    
    @property
    def update_interval_hours(self) -> int:
        return 6  # Minimum hours between updates
    
    def scrape(self) -> Dict[str, Any]:
        """
        Scrape news from the source
        
        Returns:
            Dict with format:
            {
                "success": bool,
                "articles": [
                    {
                        "id": str,           # Unique identifier
                        "title": str,        # Article title
                        "summary": str,      # Article description
                        "url": str,          # Article URL
                        "date": Optional[str], # ISO format date
                        "author": str        # Source/author name
                    }
                ],
                "error": Optional[str]
            }
        """
        try:
            # Your scraping logic here
            response = requests.get("https://example.com/news", timeout=30)
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "articles": [],
                    "error": f"HTTP {response.status_code}"
                }
            
            # Parse response and extract articles
            articles = []
            # ... parsing logic ...
            
            return {
                "success": True,
                "articles": articles,
                "error": None
            }
            
        except Exception as e:
            return {
                "success": False,
                "articles": [],
                "error": str(e)
            }
```

### 3. Handle errors gracefully

Always wrap your scraping logic in try-catch blocks and return appropriate error messages. The base class provides logging support via `self.logger`.

### 4. Respect rate limits

Implement appropriate update intervals to prevent being blocked by the target site. The base class handles timing automatically based on your `update_interval_hours` property.

## Available Scrapers

Current scrapers in this directory:

- **kyutai_scraper.py**: Scrapes news from Kyutai AI research lab blog
- **mistral_scraper.py**: Scrapes news from Mistral AI via their CMS API

## Database Integration

Scrapers don't need to handle database operations directly. The base class provides:

- `get_existing_ids()`: Get existing article IDs from database
- `save_articles()`: Save new articles to database
- `should_update()`: Check if enough time has passed
- `update()`: Complete update cycle (scrape + save)

## Error Handling

The system handles scraper failures gracefully:

- Failed scrapers don't prevent other scrapers from running
- Errors are logged but don't crash the news service
- Invalid scrapers are skipped during discovery

## Testing

Test your scraper by:

1. Running syntax validation: `python -m py_compile your_scraper.py`
2. Testing the scrape method manually
3. Checking logs for any errors during startup