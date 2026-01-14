from .base import BaseParser
from typing import Dict, Any, List
import json
import base64
import io
import os
from pathlib import Path
from pdf2image import convert_from_path
from config import Config
from PIL import Image
from llm import LLMProcessor, PdfVisionStrategy

class PdfParser(BaseParser):
    """Parser for PDF files using LLM Vision via LLMProcessor."""

    def __init__(self, data_dir: Path, output_dir: Path):
        super().__init__(data_dir, output_dir)
        self.processor = LLMProcessor() 
        self.strategy = PdfVisionStrategy()

    def parse(self) -> Dict[str, Any]:
        """Parse all PDF files using Vision."""
        pdf_files = list(self.data_dir.rglob("*.pdf"))
        results = {}
        
        print(f"Found {len(pdf_files)} PDF files to process.")
        print(f"DEBUG: Using POPPLER_PATH = {Config.POPPLER_PATH}")

        for pdf_file in pdf_files:
            part_id = pdf_file.stem
            print(f"Processing PDF: {pdf_file.name}")
            
            try:
                # Extract material info using Vision
                material_data = self._analyze_with_vision(pdf_file)
                
                results[part_id] = {
                    "material_name": material_data.get("material_name", "NOT_FOUND"),
                    "material_specifications": material_data.get("material_specifications", ""),
                    "confidence": material_data.get("confidence", "low"),
                    "file_path": str(pdf_file),
                    "full_analysis": material_data 
                }
                
                print(f"  -> Found: {results[part_id]['material_name']} (Conf: {results[part_id]['confidence']})")

            except Exception as e:
                print(f"  Error processing {pdf_file.name}: {e}")
                results[part_id] = {
                    "error": str(e), 
                    "material_name": "ERROR",
                    "file_path": str(pdf_file)
                }
                
        return results

    def _encode_image(self, image: Image.Image) -> str:
        """Convert PIL image to base64 string."""
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG')
        img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return img_str

    def _analyze_with_vision(self, pdf_path: Path) -> Dict[str, Any]:
        """Convert PDF to image and analyze via LLMProcessor."""
        
        # Convert PDF to images (only first page)
        try:
            images = convert_from_path(str(pdf_path), poppler_path=Config.POPPLER_PATH)
        except Exception as e:
            raise RuntimeError(f"Failed to convert PDF to image: {e}. Check Poppler path in config.py")

        if not images:
            return {"material_name": "ERROR", "material_specifications": "No images extracted", "confidence": "low"}

        # Only process first page
        image = images[0]
        base64_image = self._encode_image(image)

        # Generate prompt using the strategy
        prompt = self.strategy.generate_prompt()
        
        # Ask LLM via the centralized processor
        return self.processor.ask_llm(prompt, image_base64=base64_image)

