"""
News scraping extensions package
Provides automatic discovery and loading of news scrapers
"""

import os
import importlib
import importlib.util
import inspect
from typing import Dict, List, Type, Optional
from .base_scraper import BaseScraper


def discover_scrapers(scrapers_dir: Optional[str] = None) -> Dict[str, Type[BaseScraper]]:
    """
    Discover all available scraper classes in the news_scrape directory
    
    Args:
        scrapers_dir: Directory to scan for scrapers (defaults to this package directory)
        
    Returns:
        Dictionary mapping scraper names to scraper classes
    """
    scrapers = {}
    
    if scrapers_dir is None:
        scrapers_dir = os.path.dirname(__file__)
    
    # Scan for Python files in the scrapers directory
    for filename in os.listdir(scrapers_dir):
        if filename.endswith('.py') and filename != '__init__.py' and filename != 'base_scraper.py':
            module_name = filename[:-3]  # Remove .py extension
            
            try:
                # Try relative import first, then fallback to file loading
                try:
                    module = importlib.import_module(f'.{module_name}', package=__name__)
                except (ImportError, ValueError):
                    # Fallback to direct file loading
                    spec = importlib.util.spec_from_file_location(
                        module_name, 
                        os.path.join(scrapers_dir, filename)
                    )
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                
                # Find all BaseScraper subclasses in the module
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, BaseScraper) and 
                        obj != BaseScraper):
                        
                        # Get the scraper name from the class
                        instance = obj(db_path="", logger=None)  # Temporary instance for name
                        scraper_name = instance.name
                        scrapers[scraper_name] = obj
                        
            except Exception as e:
                # Log error but don't fail entire discovery
                print(f"Warning: Could not load scraper module {module_name}: {str(e)}")
    
    return scrapers


def load_scrapers(db_path: str, logger=None) -> Dict[str, BaseScraper]:
    """
    Load and instantiate all available scrapers
    
    Args:
        db_path: Path to the SQLite database
        logger: Logger instance (optional)
        
    Returns:
        Dictionary mapping scraper names to scraper instances
    """
    scraper_classes = discover_scrapers()
    scrapers = {}
    
    for name, scraper_class in scraper_classes.items():
        try:
            scraper_instance = scraper_class(db_path, logger)
            scrapers[name] = scraper_instance
            
            if logger:
                logger.info(f"Loaded news scraper: {name}", module_name="news")
                
        except Exception as e:
            if logger:
                logger.error(f"Failed to load scraper {name}: {str(e)}", module_name="news")
    
    return scrapers


def get_available_scrapers() -> List[str]:
    """
    Get list of available scraper names
    
    Returns:
        List of scraper names
    """
    scrapers = discover_scrapers()
    return list(scrapers.keys())