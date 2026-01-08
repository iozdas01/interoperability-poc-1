from .base import BaseParser
from typing import Dict, Any
import pdfplumber

class PdfParser(BaseParser):
    """Parser for PDF files to extract text content."""

    def parse(self) -> Dict[str, Any]:
        """Parse all PDF files."""
        pdf_files = list(self.data_dir.rglob("*.pdf"))
        results = {}
        
        for pdf_file in pdf_files:
            part_id = pdf_file.stem
            print(f"Processing PDF: {pdf_file.name}")
            
            try:
                text = self._extract_text(pdf_file)
                results[part_id] = {
                    "content": text,
                    "file_path": str(pdf_file)
                }
            except Exception as e:
                print(f"Error processing {pdf_file.name}: {e}")
                results[part_id] = {"error": str(e)}
                
        return results

    def _extract_text(self, pdf_path) -> str:
        text = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
        return '\n'.join(text)
