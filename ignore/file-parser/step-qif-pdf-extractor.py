#!/usr/bin/env python3
"""
Combined Parser Script
======================
This script combines all parsers (PDF, QIF, STEP) into a single executable.
It processes all supported file types and generates unified metadata output.
"""

import pdfplumber
import json
import csv
import re
import pandas as pd
from pathlib import Path
import os
import traceback
import numpy as np
from collections import Counter, defaultdict

# Try to import OCC libraries for STEP parsing
try:
    from OCC.Core.STEPControl import STEPControl_Reader, STEPControl_AsIs
    from OCC.Display.SimpleGui import init_display
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_SHAPE, TopAbs_ShapeEnum
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.GeomAdaptor import GeomAdaptor_Surface
    from OCC.Core.GeomAbs import GeomAbs_Plane
    from OCC.Core.BRepExtrema import BRepExtrema_DistShapeShape
    from OCC.Core.TopoDS import topods
    from OCC.Core.GProp import GProp_GProps
    from OCC.Core.BRepGProp import brepgprop
    from OCC.Core.gp import gp_Vec, gp_Pnt, gp_Dir
    OCC_AVAILABLE = True
except ImportError:
    print("Warning: OCC libraries not available. STEP parsing will be skipped.")
    OCC_AVAILABLE = False

# Configuration
RAW_DATA_DIR = Path("data")
OUTPUT_DIR = Path("execute/parsed-results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# STEP parser configuration
MIN_FACE_AREA = 10.0
NUM_SAMPLE_POINTS = 100000
PARALLEL_TOLERANCE = 0.01

class PDFParser:
    """PDF parser for extracting all text content."""
    
    def __init__(self, raw_data_dir, output_dir):
        self.raw_data_dir = raw_data_dir
        self.output_dir = output_dir
    
    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extract all text from a PDF file."""
        text = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
        return '\n'.join(text)
    
    def extract_text_from_csv(self, csv_path: Path) -> str:
        """Extract all text from a CSV file."""
        with open(csv_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def parse(self):
        """Parse all PDF and CSV files and extract all text content."""
        print("Starting PDF/CSV text extraction...")
        
        # Process PDF files
        pdf_files = list(self.raw_data_dir.rglob("*.pdf"))
        csv_files = list(self.raw_data_dir.rglob("*.csv"))
        
        if not pdf_files and not csv_files:
            print("No PDF or CSV files found.")
            return {}
        
        print(f"Found {len(pdf_files)} PDF files and {len(csv_files)} CSV files to process")
        
        # Extract text from all files, organized by part_id
        all_text = {}
        
        # Process PDF files
        for pdf_path in pdf_files:
            try:
                part_id = pdf_path.stem
                text_content = self.extract_text_from_pdf(pdf_path)
                
                if part_id not in all_text:
                    all_text[part_id] = {}
                
                all_text[part_id]["pdf"] = {
                    "content": text_content,
                    "file_path": str(pdf_path)
                }
                print(f"Extracted text from PDF: {pdf_path.name}")
            except Exception as e:
                print(f"Error processing PDF {pdf_path.name}: {e}")
                continue
        
        # Process CSV files
        for csv_path in csv_files:
            try:
                part_id = csv_path.stem
                text_content = self.extract_text_from_csv(csv_path)
                
                if part_id not in all_text:
                    all_text[part_id] = {}
                
                all_text[part_id]["csv"] = {
                    "content": text_content,
                    "file_path": str(csv_path)
                }
                print(f"Extracted text from CSV: {csv_path.name}")
            except Exception as e:
                print(f"Error processing CSV {csv_path.name}: {e}")
                continue
        
        return all_text

class QIFParser:
    """QIF parser for extracting material and thickness information."""
    
    def __init__(self, raw_data_dir, output_dir):
        self.raw_data_dir = raw_data_dir
        self.output_dir = output_dir
    
    def extract_material(self, line):
        """Extract material from QIF line."""
        match = re.search(r"<Text>Material:\s*(.*?)</Text>", line, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None
    
    def extract_thickness(self, line):
        """Extract thickness from QIF line."""
        match = re.search(r"<Text>Thickness:\s*([\d.,]+\s*mm)", line, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None
    
    def parse(self):
        """Parse all QIF files and extract metadata."""
        print("Starting QIF parsing...")
        
        qif_files = list(self.raw_data_dir.rglob("*.qif"))
        
        if not qif_files:
            print("No QIF files found.")
            return {}
        
        print(f"Found {len(qif_files)} QIF files to process")
        
        # Organize results by part_id
        all_qif_data = {}
        
        for qif_path in qif_files:
            try:
                part_id = qif_path.stem
                material = None
                thickness = None
                
                with open(qif_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if material is None:
                            m = self.extract_material(line)
                            if m:
                                material = m
                        if thickness is None:
                            t = self.extract_thickness(line)
                            if t:
                                thickness = t
                        if material and thickness:
                            break
                
                all_qif_data[part_id] = {
                    "material": material or "N/A",
                    "thickness": thickness or "N/A",
                    "file_path": str(qif_path)
                }
                print(f"Extracted from {qif_path.name}: material={material}, thickness={thickness}")
            except Exception as e:
                print(f"Error processing QIF {qif_path.name}: {e}")
                continue
        
        return all_qif_data

class STEPParser:
    """STEP parser for extracting thickness information from 3D models."""
    
    def __init__(self, raw_data_dir, output_dir):
        self.raw_data_dir = raw_data_dir
        self.output_dir = output_dir
    
    def get_face_area(self, face):
        """Calculate the area of a face in mm²."""
        props = GProp_GProps()
        brepgprop.SurfaceProperties(face, props)
        return props.Mass()
    
    def calculate_distance_between_faces(self, face1, face2):
        """Calculate the distance between two faces using BRepExtrema_DistShapeShape."""
        try:
            dist_calc = BRepExtrema_DistShapeShape(face1, face2)
            dist_calc.Perform()
            
            if dist_calc.IsDone():
                distance = dist_calc.Value()
                return round(distance, 3)
            return None
        except Exception as e:
            print(f"Error calculating distance: {str(e)}")
            return None
    
    def analyze_distances(self, all_distances, face_pairs):
        """Analyze distances using multi-signal voting logic to determine sheet metal thickness."""
        if not all_distances:
            return None, 0, "No distances found"
        
        # Sheet metal thickness range in mm
        MIN_SHEET_THICKNESS = 0.6
        MAX_SHEET_THICKNESS = 25
        
        # Step 1: Filter distances within valid range and build area-weighted clusters
        thickness_clusters = defaultdict(float)
        filtered_distances = []
        
        for (face1, face2), distance in zip(face_pairs, all_distances):
            if MIN_SHEET_THICKNESS <= distance <= MAX_SHEET_THICKNESS:
                area1 = self.get_face_area(face1)
                area2 = self.get_face_area(face2)
                total_area = area1 + area2
                
                rounded_distance = round(distance, 2)
                thickness_clusters[rounded_distance] += total_area
                filtered_distances.append(rounded_distance)
        
        if not filtered_distances:
            return None, 0, f"No valid thickness found in range {MIN_SHEET_THICKNESS}-{MAX_SHEET_THICKNESS} mm"
        
        # Step 2: Calculate key metrics
        min_thickness = min(filtered_distances)
        hist = Counter(filtered_distances)
        mode_thickness, mode_count = hist.most_common(1)[0]
        total = len(filtered_distances)
        mode_frequency = mode_count / total
        area_thickness = max(thickness_clusters.items(), key=lambda x: x[1])[0]
        
        # Step 3: Calculate confidence scores
        def calculate_confidence_score(thickness, frequency, area, min_thickness):
            norm_freq = frequency
            norm_area = area / max(thickness_clusters.values())
            norm_closeness = 1 - (abs(thickness - min_thickness) / min_thickness)
            
            alpha = 0.4  # frequency weight
            beta = 0.3   # area weight
            gamma = 0.3  # closeness to min weight
            
            return (alpha * norm_freq + beta * norm_area + gamma * norm_closeness)
        
        candidates = set(filtered_distances)
        scores = {}
        for thickness in candidates:
            freq = hist[thickness] / total
            area = thickness_clusters[thickness]
            scores[thickness] = calculate_confidence_score(thickness, freq, area, min_thickness)
        
        # Step 4: Decision logic
        min_area = thickness_clusters[min_thickness]
        area_dominant_area = thickness_clusters[area_thickness]
        area_min_ratio = area_thickness / min_thickness
        mode_min_ratio = mode_thickness / min_thickness
        
        if area_min_ratio < 1.4:
            thickness = area_thickness
            method = f"Using area-dominant (close to min: ratio {area_min_ratio:.2f}x)"
        elif min_thickness < 1.5 and mode_min_ratio > 1.5:
            thickness = min_thickness
            method = f"Using min (small thickness {min_thickness:.2f}mm with larger mode {mode_thickness:.2f}mm)"
        elif mode_frequency > 0.4 and abs(mode_thickness - area_thickness) < 0.1:
            thickness = mode_thickness
            method = f"Using mode (strong frequency {mode_frequency:.2f} and agrees with area-dominant)"
        else:
            thickness = max(scores.items(), key=lambda x: x[1])[0]
            method = f"Using highest confidence score ({scores[thickness]:.2f})"
        
        return thickness, hist[thickness], method
    
    def verify_parallelism_with_points(self, face1, face2, plane1, plane2, num_points=10):
        """Verify parallelism by checking multiple points on the faces."""
        try:
            surface1 = BRep_Tool.Surface(face1)
            u1, u2, v1, v2 = surface1.Bounds()
            
            u_values = np.linspace(u1, u2, num_points)
            v_values = np.linspace(v1, v2, num_points)
            
            distances = []
            for u in u_values:
                for v in v_values:
                    try:
                        pnt = surface1.Value(u, v)
                        dist = abs(plane2.Distance(pnt))
                        distances.append(dist)
                    except:
                        continue
            
            if not distances:
                return False
            
            mean_dist = sum(distances) / len(distances)
            max_deviation = mean_dist * 0.01
            
            return all(abs(d - mean_dist) <= max_deviation for d in distances)
        except Exception as e:
            print(f"Error verifying parallelism with points: {str(e)}")
            return False
    
    def parse(self):
        """Parse all STEP files and extract thickness information."""
        if not OCC_AVAILABLE:
            print("STEP parsing skipped - OCC libraries not available.")
            return {}
        
        print("Starting STEP parsing...")
        
        step_files = [f for f in self.raw_data_dir.rglob("*") 
                     if f.suffix.lower() in {'.step', '.stp', '.STEP'}]
        
        if not step_files:
            print("No STEP files found.")
            return {}
        
        print(f"Found {len(step_files)} STEP files to process")
        
        # Organize results by part_id
        all_step_data = {}
        
        for step_file in step_files:
            try:
                part_id = step_file.stem
                print(f"\nProcessing: {step_file.name}")
                
                # Load the STEP file
                step_reader = STEPControl_Reader()
                status = step_reader.ReadFile(str(step_file))
                
                if status != 1:
                    print(f"Failed to read STEP file: {step_file.name}")
                    all_step_data[part_id] = {
                        'thickness': 'Read Error',
                        'occurrence_count': 0,
                        'all_distances': 'N/A',
                        'analysis_method': 'N/A',
                        'file_path': str(step_file)
                    }
                    continue
                
                step_reader.TransferRoot()
                shape = step_reader.OneShape()
                
                if shape is None:
                    print(f"Warning: Shape is None for {step_file.name}")
                    all_step_data[part_id] = {
                        'thickness': 'No Shape',
                        'occurrence_count': 0,
                        'all_distances': 'N/A',
                        'analysis_method': 'N/A',
                        'file_path': str(step_file)
                    }
                    continue
                
                # Extract faces
                faces = []
                try:
                    explorer = TopExp_Explorer(shape, TopAbs_ShapeEnum(TopAbs_FACE), TopAbs_ShapeEnum(TopAbs_SHAPE))
                    
                    while explorer.More():
                        face = topods.Face(explorer.Current())
                        area = self.get_face_area(face)
                        if area >= MIN_FACE_AREA:
                            faces.append(face)
                        explorer.Next()
                    
                    print(f"Found {len(faces)} faces (after filtering small faces)")
                except Exception as e:
                    print(f"Error during face exploration: {str(e)}")
                    all_step_data[part_id] = {
                        'thickness': 'Face Error',
                        'occurrence_count': 0,
                        'all_distances': 'N/A',
                        'analysis_method': 'N/A',
                        'file_path': str(step_file)
                    }
                    continue
                
                # Find parallel planar surfaces
                all_distances = []
                face_pairs = []
                
                for i, face1 in enumerate(faces):
                    try:
                        surface1 = BRep_Tool.Surface(face1)
                        adaptor1 = GeomAdaptor_Surface(surface1)
                        
                        if adaptor1.GetType() != GeomAbs_Plane:
                            continue
                        
                        plane1 = adaptor1.Plane()
                        normal1 = plane1.Axis().Direction()
                        
                        for j in range(i+1, len(faces)):
                            try:
                                face2 = faces[j]
                                surface2 = BRep_Tool.Surface(face2)
                                adaptor2 = GeomAdaptor_Surface(surface2)
                                
                                if adaptor2.GetType() != GeomAbs_Plane:
                                    continue
                                
                                plane2 = adaptor2.Plane()
                                normal2 = plane2.Axis().Direction()
                                
                                dot_product = normal1.Dot(normal2)
                                
                                if abs(abs(dot_product) - 1.0) < PARALLEL_TOLERANCE:
                                    if self.verify_parallelism_with_points(face1, face2, plane1, plane2, num_points=10):
                                        print(f"Found parallel faces {i} and {j} with dot product: {dot_product}")
                                        
                                        distance = self.calculate_distance_between_faces(face1, face2)
                                        if distance is not None:
                                            print(f"Distance between faces {i} and {j}: {distance} mm")
                                            all_distances.append(distance)
                                            face_pairs.append((face1, face2))
                            except Exception as e:
                                print(f"Error processing face pair {i}-{j}: {str(e)}")
                                continue
                    except Exception as e:
                        print(f"Error processing face {i}: {str(e)}")
                        continue
                
                print(f"Found {len(face_pairs)} pairs of parallel faces")
                
                if all_distances:
                    thickness, count, method = self.analyze_distances(all_distances, face_pairs)
                    
                    if thickness is not None:
                        all_step_data[part_id] = {
                            'thickness': thickness,
                            'occurrence_count': count,
                            'all_distances': ', '.join(map(str, sorted(set(all_distances)))),
                            'analysis_method': method,
                            'file_path': str(step_file)
                        }
                        print(f"Determined thickness: {thickness} mm (occurs {count} times)")
                    else:
                        all_step_data[part_id] = {
                            'thickness': 'No Consistent Thickness',
                            'occurrence_count': 0,
                            'all_distances': ', '.join(map(str, sorted(set(all_distances)))),
                            'analysis_method': method,
                            'file_path': str(step_file)
                        }
                else:
                    all_step_data[part_id] = {
                        'thickness': 'No Parallel Faces',
                        'occurrence_count': 0,
                        'all_distances': 'N/A',
                        'analysis_method': 'N/A',
                        'file_path': str(step_file)
                    }
            except Exception as e:
                print(f"Error processing file {step_file.name}: {str(e)}")
                all_step_data[step_file.stem] = {
                    'thickness': 'Processing Error',
                    'occurrence_count': 0,
                    'all_distances': 'N/A',
                    'analysis_method': 'N/A',
                    'file_path': str(step_file)
                }
        
        return all_step_data

class CombinedParser:
    """Main class that combines all parsers and provides unified output."""
    
    def __init__(self, raw_data_dir=None, output_dir=None, subdirectory=None):
        self.raw_data_dir = raw_data_dir or RAW_DATA_DIR
        self.subdirectory = subdirectory
        self.output_dir = output_dir or OUTPUT_DIR
        
        # If subdirectory is specified, update the raw_data_dir path
        if self.subdirectory:
            self.raw_data_dir = self.raw_data_dir / self.subdirectory
            # Update output directory to include subdirectory name
            self.output_dir = self.output_dir / self.subdirectory
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize individual parsers
        self.pdf_parser = PDFParser(self.raw_data_dir, self.output_dir)
        self.qif_parser = QIFParser(self.raw_data_dir, self.output_dir)
        self.step_parser = STEPParser(self.raw_data_dir, self.output_dir)
    
    def parse_all(self):
        """Run all parsers and combine results by part."""
        print("=" * 60)
        print(f"COMBINED PARSER - Processing files from: {self.raw_data_dir}")
        print("=" * 60)
        
        # Run all parsers
        pdf_data = {}
        qif_data = {}
        step_data = {}
        
        try:
            pdf_data = self.pdf_parser.parse()
            print(f"PDF parser completed: {len(pdf_data)} parts")
        except Exception as e:
            print(f"PDF parser failed: {e}")
        
        try:
            qif_data = self.qif_parser.parse()
            print(f"QIF parser completed: {len(qif_data)} parts")
        except Exception as e:
            print(f"QIF parser failed: {e}")
        
        try:
            step_data = self.step_parser.parse()
            print(f"STEP parser completed: {len(step_data)} parts")
        except Exception as e:
            print(f"STEP parser failed: {e}")
        
        # Combine all data by part
        all_parts = set(list(pdf_data.keys()) + list(qif_data.keys()) + list(step_data.keys()))
        
        print(f"\nCreating output files for {len(all_parts)} parts...")
        
        # Create one file per part
        for part_id in all_parts:
            part_data = {
                "part_id": part_id,
                "pdf_data": pdf_data.get(part_id, {}),
                "qif_data": qif_data.get(part_id, {}),
                "step_data": step_data.get(part_id, {})
            }
            
            # Save JSON file for this part
            json_path = self.output_dir / f"{part_id}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(part_data, f, indent=2, ensure_ascii=False)
            
            # Save TXT file for this part
            txt_path = self.output_dir / f"{part_id}.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(f"=== PART: {part_id} ===\n\n")
                
                # PDF data
                if part_data["pdf_data"]:
                    f.write("PDF DATA:\n")
                    f.write("-" * 20 + "\n")
                    for file_type, data in part_data["pdf_data"].items():
                        f.write(f"File Type: {file_type.upper()}\n")
                        f.write(f"File Path: {data['file_path']}\n")
                        f.write("Content:\n")
                        f.write(data['content'])
                        f.write("\n\n")
                
                # QIF data
                if part_data["qif_data"]:
                    f.write("QIF DATA:\n")
                    f.write("-" * 20 + "\n")
                    f.write(f"Material: {part_data['qif_data'].get('material', 'N/A')}\n")
                    f.write(f"Thickness: {part_data['qif_data'].get('thickness', 'N/A')}\n")
                    f.write(f"File Path: {part_data['qif_data'].get('file_path', 'N/A')}\n\n")
                
                # STEP data
                if part_data["step_data"]:
                    f.write("STEP DATA:\n")
                    f.write("-" * 20 + "\n")
                    f.write(f"Thickness: {part_data['step_data'].get('thickness', 'N/A')}\n")
                    f.write(f"Occurrence Count: {part_data['step_data'].get('occurrence_count', 'N/A')}\n")
                    f.write(f"All Distances: {part_data['step_data'].get('all_distances', 'N/A')}\n")
                    f.write(f"Analysis Method: {part_data['step_data'].get('analysis_method', 'N/A')}\n")
                    f.write(f"File Path: {part_data['step_data'].get('file_path', 'N/A')}\n\n")
            
            print(f"Created files for {part_id}: {json_path.name}, {txt_path.name}")
        
        print(f"\nAll files saved to: {self.output_dir}")
        print(f"Total parts processed: {len(all_parts)}")
        
        return all_parts

def main():
    """Main function to run the combined parser."""
    # Start with AutoCAD folder
    parser = CombinedParser(subdirectory="teknocer")
    results = parser.parse_all()
    
    print("\n" + "=" * 60)
    print("COMBINED PARSER COMPLETED")
    print("=" * 60)
    
    return results

if __name__ == "__main__":
    main()
