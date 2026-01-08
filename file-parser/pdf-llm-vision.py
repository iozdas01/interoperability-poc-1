import os
import glob
import json
import base64
from pdf2image import convert_from_path
from openai import OpenAI
from PIL import Image
import io

def encode_image(image):
    """Convert PIL image to base64 string."""
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG')
    img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return img_str

def extract_material_from_pdf_image(pdf_file, client):
    """Extract material information from PDF using LLM vision."""
    
    pdf_name = os.path.basename(pdf_file)
    pdf_name_no_ext = os.path.splitext(pdf_name)[0]
    
    print(f"\nProcessing: {pdf_name}")
    print(f"File size: {os.path.getsize(pdf_file)} bytes")
    
    try:
        # Convert PDF to images (only first page)
        print("  Converting PDF to images...")
        images = convert_from_path(pdf_file, poppler_path=r'C:\Users\Izgin\anaconda3\envs\pyoccenv\Library\bin')
        print(f"  Converted {len(images)} pages to images")
        
        # Only process the first page
        if images:
            images = [images[0]]  # Take only the first page
            print(f"  Processing only first page for efficiency")
        
        all_materials = []
        
        for page_num, image in enumerate(images):
            print(f"  Analyzing page {page_num + 1} with LLM vision...")
            
            # Encode image for LLM
            base64_image = encode_image(image)
            
            # Create prompt for material extraction
            prompt = """Analyze this technical drawing/PDF page and extract material information.

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
  "page_number": page_number,
  "confidence": "high/medium/low"
}

If no material information is found, return:
{
  "material_name": "NOT_FOUND",
  "material_specifications": "No material information detected on this page",
  "page_number": page_number,
  "confidence": "low"
}"""
            
            try:
                # Call LLM with vision
                response = client.chat.completions.create(
                    model="gpt-4o-mini",  # Use vision-capable model
                    max_tokens=500,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ]
                )
                
                # Parse the response
                response_text = response.choices[0].message.content.strip()
                
                # Try to extract JSON from response
                try:
                    # Clean up the response if it has markdown formatting
                    if response_text.startswith('```json'):
                        response_text = response_text[7:]
                    if response_text.endswith('```'):
                        response_text = response_text[:-3]
                    
                    material_data = json.loads(response_text)
                    material_data['page_number'] = page_num + 1
                    all_materials.append(material_data)
                    
                    print(f"    ✓ Page {page_num + 1}: {material_data.get('material_name', 'Unknown')}")
                    print(f"    Confidence: {material_data.get('confidence', 'Unknown')}")
                    
                except json.JSONDecodeError as e:
                    print(f"    ⚠ JSON parsing error on page {page_num + 1}: {e}")
                    print(f"    Raw response: {response_text[:200]}...")
                    
                    # Create fallback data
                    fallback_data = {
                        "material_name": "PARSE_ERROR",
                        "material_specifications": f"Failed to parse LLM response: {response_text[:100]}",
                        "page_number": page_num + 1,
                        "confidence": "low"
                    }
                    all_materials.append(fallback_data)
                
            except Exception as e:
                print(f"    ✗ Error processing page {page_num + 1}: {e}")
                fallback_data = {
                    "material_name": "ERROR",
                    "material_specifications": f"Error: {str(e)}",
                    "page_number": page_num + 1,
                    "confidence": "low"
                }
                all_materials.append(fallback_data)
        
        # Combine results from all pages
        if all_materials:
            # Find the best material result (highest confidence, not NOT_FOUND)
            best_material = None
            for material in all_materials:
                if (material.get('material_name') != 'NOT_FOUND' and 
                    material.get('material_name') != 'PARSE_ERROR' and
                    material.get('material_name') != 'ERROR'):
                    if best_material is None or material.get('confidence') == 'high':
                        best_material = material
            
            if best_material is None:
                # If no good material found, use the first one
                best_material = all_materials[0]
            
            return {
                "pdf_file": pdf_name,
                "step_file": pdf_name_no_ext,  # Use PDF name as STEP file name
                "material_name": best_material.get('material_name', 'UNKNOWN'),
                "material_specifications": best_material.get('material_specifications', ''),
                "all_pages_analysis": all_materials,
                "best_confidence": best_material.get('confidence', 'low')
            }
        else:
            return {
                "pdf_file": pdf_name,
                "step_file": pdf_name_no_ext,
                "material_name": "NO_MATERIAL_FOUND",
                "material_specifications": "No material information extracted from any page",
                "all_pages_analysis": [],
                "best_confidence": "low"
            }
            
    except Exception as e:
        print(f"  ✗ Error processing {pdf_name}: {e}")
        return {
            "pdf_file": pdf_name,
            "step_file": pdf_name_no_ext,
            "material_name": "ERROR",
            "material_specifications": f"Processing error: {str(e)}",
            "all_pages_analysis": [],
            "best_confidence": "low"
        }

def process_all_pdfs():
    """Process all PDFs using LLM vision."""
    
    # Initialize OpenAI client
    client = OpenAI()
    
    # Hardcoded path to the RAW PDF files
    unannotated_dir = "exploring-files/Raw-Data-UW/unannotated"
    pdf_files = glob.glob(os.path.join(unannotated_dir, "*.pdf"))
    print(f"Found {len(pdf_files)} PDF files in {unannotated_dir}")
    
    if not pdf_files:
        print("No PDF files found!")
        return
    
    # Create output directory for individual material files
    output_dir = "exploring-files/llm-inputs-pdf"
    os.makedirs(output_dir, exist_ok=True)
    
    all_results = []
    
    # Process each PDF
    for pdf_file in pdf_files:
        result = extract_material_from_pdf_image(pdf_file, client)
        all_results.append(result)
        
        # Save individual result
        pdf_name_no_ext = os.path.splitext(os.path.basename(pdf_file))[0]
        individual_file = os.path.join(output_dir, f"{pdf_name_no_ext}_material.json")
        
        with open(individual_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"  ✓ Saved material analysis to: {individual_file}")
    
    print(f"\nVision analysis complete!")
    print(f"Individual material files saved to: {output_dir}")
    print("Each file contains the extracted material information for one PDF.")
    
    # Print summary
    print(f"\nSummary:")
    for result in all_results:
        pdf_name = result['pdf_file']
        material = result['material_name']
        confidence = result['best_confidence']
        print(f"  {pdf_name}: {material} (confidence: {confidence})")

if __name__ == "__main__":
    print("PDF LLM Vision Material Extractor")
    print("=" * 50)
    process_all_pdfs() 