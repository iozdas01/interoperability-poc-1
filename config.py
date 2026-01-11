from pathlib import Path
import os
from dotenv import load_dotenv

# Load variables from .env file if it exists
load_dotenv()

class Config:
    """Central configuration for the DXF Interoperability Project."""
    
    # Base Directories
    BASE_DIR = Path(__file__).resolve().parent
    DATA_DIR = BASE_DIR / "data"
    EXECUTE_DIR = BASE_DIR / "execute"
    
    # Output Directories
    PARSED_RESULTS_DIR = EXECUTE_DIR / "parsed-results"
    LLM_RESULTS_DIR = EXECUTE_DIR / "llm-results"
    
    # Ensure directories exist
    PARSED_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    LLM_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Settings
    CAM_SOFTWARE = "CypCut"
    
    # Parser Settings
    STEP_MIN_FACE_AREA = 10.0
    STEP_NUM_SAMPLE_POINTS = 100000
    STEP_PARALLEL_TOLERANCE = 0.01

    # External Tools
    # Read from .env, with your specific machine path as a fallback
    POPPLER_PATH = os.getenv(
        "POPPLER_PATH", 
        r"C:\Users\Izgin\anaconda3\envs\pyoccenv\Library\bin"
    )
    
    @classmethod
    def get_input_dir(cls, subdirectory: str) -> Path:
        """Get the full path for an input subdirectory (e.g., 'teknocer')."""
        return cls.DATA_DIR / subdirectory

    @classmethod
    def get_output_dir(cls, subdirectory: str) -> Path:
        """Get the full path for output results for a subdirectory."""
        return cls.PARSED_RESULTS_DIR / subdirectory
