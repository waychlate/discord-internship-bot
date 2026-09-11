from abc import ABC, abstractmethod
from typing import Dict, List
from src.models import JobPosting


class BaseSource(ABC):
    def __init__(self, name: str, config: Dict):
        self.name = name
        self.config = config

    @abstractmethod
    def fetch_jobs(self) -> List[JobPosting]:
        """Fetch and return a list of JobPosting objects from this source."""
        pass

