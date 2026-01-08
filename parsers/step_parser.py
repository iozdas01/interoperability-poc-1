from .base import BaseParser
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from collections import defaultdict, Counter
import numpy as np

try:
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_SHAPE, TopAbs_ShapeEnum
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.GeomAdaptor import GeomAdaptor_Surface
    from OCC.Core.GeomAbs import GeomAbs_Plane
    from OCC.Core.BRepExtrema import BRepExtrema_DistShapeShape
    from OCC.Core.TopoDS import topods
    from OCC.Core.GProp import GProp_GProps
    from OCC.Core.BRepGProp import brepgprop
    OCC_AVAILABLE = True
except ImportError:
    OCC_AVAILABLE = False
    print("Warning: OCC libraries not available. STEP parsing will be skipped.")

class StepParser(BaseParser):
    """Parser for STEP files to extract geometric thickness."""
    
    MIN_FACE_AREA = 10.0
    PARALLEL_TOLERANCE = 0.01
    
    def parse(self) -> Dict[str, Any]:
        """Parse all STEP files in the data directory."""
        if not OCC_AVAILABLE:
            return {}
            
        step_files = [f for f in self.data_dir.rglob("*") 
                     if f.suffix.lower() in {'.step', '.stp', '.STEP'}]
        
        results = {}
        for step_file in step_files:
            part_id = step_file.stem
            print(f"Processing STEP: {step_file.name}")
            
            try:
                data = self._process_single_file(step_file)
                results[part_id] = data
            except Exception as e:
                print(f"Error processing {step_file.name}: {e}")
                results[part_id] = {"error": str(e)}
                
        return results

    def _process_single_file(self, step_file: Path) -> Dict[str, Any]:
        """Process a single STEP file."""
        import sys
        
        reader = STEPControl_Reader()
        status = reader.ReadFile(str(step_file))
        
        if status != 1:
            return {"thickness": "Read Error"}
            
        reader.TransferRoot()
        shape = reader.OneShape()
        
        if shape is None:
            return {"thickness": "No Shape"}
            
        faces = self._extract_faces(shape)
        if not faces:
            return {"thickness": "No Faces"}
            
        thickness, count, method = self._calculate_thickness(faces)
        
        return {
            "thickness": thickness,
            "occurrence_count": count,
            "analysis_method": method,
            "file_path": str(step_file)
        }

    def _extract_faces(self, shape):
        """Extract valid faces from shape."""
        faces = []
        explorer = TopExp_Explorer(shape, TopAbs_ShapeEnum(TopAbs_FACE), TopAbs_ShapeEnum(TopAbs_SHAPE))
        while explorer.More():
            face = topods.Face(explorer.Current())
            props = GProp_GProps()
            brepgprop.SurfaceProperties(face, props)
            if props.Mass() >= self.MIN_FACE_AREA:
                faces.append(face)
            explorer.Next()
        return faces

    def _calculate_thickness(self, faces) -> Tuple[Any, int, str]:
        """Calculate thickness from faces."""
        all_distances = []
        face_pairs = []
        
        for i, face1 in enumerate(faces):
            # Check if planar
            surf1 = BRep_Tool.Surface(face1)
            if GeomAdaptor_Surface(surf1).GetType() != GeomAbs_Plane:
                continue
                
            plane1 = GeomAdaptor_Surface(surf1).Plane()
            normal1 = plane1.Axis().Direction()
            
            for j in range(i+1, len(faces)):
                face2 = faces[j]
                surf2 = BRep_Tool.Surface(face2)
                if GeomAdaptor_Surface(surf2).GetType() != GeomAbs_Plane:
                    continue
                    
                plane2 = GeomAdaptor_Surface(surf2).Plane()
                normal2 = plane2.Axis().Direction()
                
                # Check parallelism
                if abs(abs(normal1.Dot(normal2)) - 1.0) < self.PARALLEL_TOLERANCE:
                    dist_calc = BRepExtrema_DistShapeShape(face1, face2)
                    dist_calc.Perform()
                    if dist_calc.IsDone():
                        dist = round(dist_calc.Value(), 3)
                        all_distances.append(dist)
                        face_pairs.append((face1, face2))

        if not all_distances:
            return None, 0, "No parallel faces"
            
        # Analyze distances (simplified voting logic)
        # Filter valid sheet metal range
        valid_distances = [d for d in all_distances if 0.5 <= d <= 25.0]
        
        if not valid_distances:
            return None, 0, "No valid thickness"
            
        # Use simple mode for now
        hist = Counter(valid_distances)
        best_thickness, count = hist.most_common(1)[0]
        
        return best_thickness, count, "Mode"
