from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Union
import json

class BaseParser(ABC):
    """Abstract base class for all file parsers."""
    
    def __init__(self, data_dir: Path, output_dir: Path):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    @abstractmethod
    def parse(self) -> Dict[str, Any]:
        """
        Parse files and return structured data.
        
        Returns:
            Dict[str, Any]: Data keyed by part_id.
        """
        pass
    
    def save_json(self, data: Dict[str, Any], filename: str) -> Path:
        """Helper to save data as JSON."""
        output_path = self.output_dir / filename
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return output_path
