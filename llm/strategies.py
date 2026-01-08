from abc import ABC, abstractmethod
from typing import Dict, Any
import json

class AnnotationStrategy(ABC):
    """Abstract base strategy for generating DXF annotations."""
    
    @abstractmethod
    def generate_prompt(self, metadata: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        pass

class ZeroShotStrategy(AnnotationStrategy):
    """Zero-shot prompting strategy."""
    
    def generate_prompt(self, metadata: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        return f"""
You are "DXF-Meta-Annotator".
OBJECTIVE: Extract material, thickness (mm), and part-ID.
OUTPUT: JSON instructions for header updates and layer renames.

METADATA:
{json.dumps(metadata, indent=2)}

Generate JSON instructions to:
1. Update $USERR1 (thicknes) and $USERI1 (part_id).
2. Rename Layer 0.
"""

class FewShotStrategy(AnnotationStrategy):
    """Few-shot prompting strategy with examples."""
    
    def generate_prompt(self, metadata: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        return f"""
You are "DXF-Meta-Annotator".
Here are examples of valid DXF structure:
Example 1: ...

METADATA:
{json.dumps(metadata, indent=2)}

Generate JSON instructions based on the examples above.
"""

class RAGStrategy(AnnotationStrategy):
    """RAG-based strategy using DXF structure context."""
    
    def generate_prompt(self, metadata: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        dxf_structure = context.get('dxf_structure', {}) if context else {}
        return f"""
You are "DXF-Meta-Annotator".
Use the EXISTING DXF STRUCTURE to determine if variables need updating or creating.

CURRENT DXF STRUCTURE:
{json.dumps(dxf_structure, indent=2)}

METADATA:
{json.dumps(metadata, indent=2)}

Generate JSON instructions.
"""

class PdfVisionStrategy(AnnotationStrategy):
    """Strategy for extracting material info from PDF drawings using Vision."""
    
    def generate_prompt(self, metadata: Dict[str, Any] = None, context: Dict[str, Any] = None) -> str:
        return """Analyze this technical drawing/PDF page and extract material information.

Look for:
1. Material names (could be in any language or could simply be numbers - English, German, French, etc.)
2. Material names are under the section that says "Material" in any language
2. Material specifications
3. Any material-related text in the document

Focus on sections that might be labeled as "Material", "Werkstoff", "Matériau", or similar terms in any language.

Return ONLY a JSON object with this structure:
{
  "material_name": "exact material name found",
  "material_specifications": "any additional material details",
  "confidence": "high/medium/low"
}

If no material information is found, return:
{
  "material_name": "NOT_FOUND",
  "material_specifications": "No material information detected on this page",
  "confidence": "low"
}"""
