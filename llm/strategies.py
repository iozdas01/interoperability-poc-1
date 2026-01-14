from abc import ABC, abstractmethod
from typing import Dict, Any
import json

class AnnotationStrategy(ABC):
    """Abstract base strategy for generating DXF annotations."""
    
    @abstractmethod
    def generate_prompt(self, metadata: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        pass

class ZeroShotStrategy(AnnotationStrategy):
    """Zero-shot prompting strategy with full DXF annotation instructions."""
    
    PROMPT_TEMPLATE = """
You are "DXF-Meta-Annotator", a tool that provides a JSON file carrying instructions to insert manufacturing metadata into DXF files compatible with CAM software.

INPUTS YOU RECEIVE:
• QIF metadata (material, thickness)
• STEP metadata (thickness from 3D geometry)
• PDF material info (from vision extraction)

OBJECTIVE
Extract material type (string), thickness (mm) (numeric), and part-ID (string or numeric), then describe how they must be embedded in the DXF so that any CAM system can read or fall back on them.

MANDATORY STORAGE RULES

1. Header Variables
   • $USERI1 (70, integer): store the numeric portion of the part-ID (extract digits from filename; if none, set 0)
   • $USERR1 (40, real): store thickness in millimetres
   Constraints:
   • Do not use any other $USER* variables (no string header slots exist).

2. Comment Records
   • Use group code 999 for comments
   • Each comment ≤ 256 characters; include full part-ID string, material, thickness_mm
   • Placement keys:
     o "file_start": immediately before first 0 SECTION
     o "file_end": immediately before final 0 EOF

3. Layer Naming
   • In the TABLES section, locate the first 0 LAYER record (Layer 0)
   • Rename to: MAT_<material>__THK_<thickness_mm>mm__PART_<part_id>
   • Obey char limits (31 for R12, 255 for R13+); avoid `<>/\\":;?*|=`
   • Placement key: "inside_LAYER_record_0"

4. Geometry Safety
   • Do not modify geometry or entity tags; only metadata fields

OUTPUT FORMAT (JSON)
Return ONLY the annotation instructions object with these keys:

{{
  "header_updates": [
    {{"var": "$USERI1", "gcode": 70, "value": <int>, "placement": "before_endsec"|"update_existing"}},
    {{"var": "$USERR1", "gcode": 40, "value": <float>, "placement": "before_endsec"|"update_existing"}}
  ],
  "layer_renames": [
    {{"index": 0, "new": "MAT_<material>__THK_<thickness_mm>mm__PART_<part_id>", "placement": "inside_LAYER_record_0"}}
  ],
  "add_comments": [
    {{"comment": "Material: <material>, Thickness: <thickness_mm>mm, Part ID: <full_part_id>", "placement": "file_start"|"file_end"}}
  ]
}}

Do not include extra keys, DXF snippets, or prose.

CONTEXT PRIORITY FOR METADATA VALUES
(1) QIF block = most reliable for material + thickness
(2) STEP block = most reliable backup for thickness (derived from 3-D geometry)
(3) PDF = use only if a value is missing from QIF/STEP

RETURN ONLY THE JSON OBJECT

--- QIF METADATA ---
{qif_metadata}

--- STEP METADATA ---
{step_metadata}

--- PDF MATERIAL INFO ---
{pdf_metadata}

--- TARGET CAM SOFTWARE ---
{cam}
"""
    
    def generate_prompt(self, metadata: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """Generate the zero-shot DXF annotation prompt."""
        # Extract data from different sources
        qif_data = metadata.get('qif', {})
        step_data = metadata.get('step', {})
        pdf_data = metadata.get('pdf', {})
        
        # Get CAM software from context or use default
        cam = context.get('cam', 'CypCut') if context else 'CypCut'
        
        return self.PROMPT_TEMPLATE.format(
            qif_metadata=json.dumps(qif_data, indent=2),
            step_metadata=json.dumps(step_data, indent=2),
            pdf_metadata=json.dumps(pdf_data, indent=2),
            cam=cam
        )


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
