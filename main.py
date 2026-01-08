import sys
import argparse
from pathlib import Path
from config import Config
from parsers import StepParser, QifParser, PdfParser, DxfParser
from llm import LLMProcessor, ZeroShotStrategy, FewShotStrategy, RAGStrategy

def run_parser_pipeline(subdirectory: str):
    """Run all parsers and aggregate data."""
    input_dir = Config.get_input_dir(subdirectory)
    output_dir = Config.get_output_dir(subdirectory)
    
    print(f"🚀 Starting Parser Pipeline for {subdirectory}")
    print(f"📂 Input: {input_dir}")
    print(f"📂 Output: {output_dir}")
    
    # Initialize parsers
    step_parser = StepParser(input_dir, output_dir)
    qif_parser = QifParser(input_dir, output_dir)
    pdf_parser = PdfParser(input_dir, output_dir)
    dxf_parser = DxfParser(input_dir, output_dir)
    
    # Run parsers
    print("\n--- Parsing Files ---")
    step_data = step_parser.parse()
    qif_data = qif_parser.parse()
    pdf_data = pdf_parser.parse()
    dxf_data = dxf_parser.parse()
    
    # Aggregate results by Part ID
    all_parts = set(step_data.keys()) | set(qif_data.keys()) | set(pdf_data.keys()) | set(dxf_data.keys())
    
    aggregated_results = {}
    for part_id in all_parts:
        aggregated_results[part_id] = {
            "step": step_data.get(part_id, {}),
            "qif": qif_data.get(part_id, {}),
            "pdf": pdf_data.get(part_id, {}),
            "dxf_structure": dxf_data.get(part_id, {})
        }
        
    print(f"\n✅ Parsed {len(aggregated_results)} parts. Saving to disk...")
    
    import json
    for part_id, data in aggregated_results.items():
        output_file = output_dir / f"{part_id}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved {output_file.name}")
    return aggregated_results, output_dir

def run_llm_pipeline(data: dict, output_dir: Path, strategy_name: str):
    """Run LLM processing using the selected strategy."""
    print(f"\n--- Running LLM Pipeline ({strategy_name}) ---")
    
    processor = LLMProcessor()
    
    # Select Strategy
    if strategy_name == "zero-shot":
        strategy = ZeroShotStrategy()
    elif strategy_name == "few-shot":
        strategy = FewShotStrategy()
    elif strategy_name == "rag":
        strategy = RAGStrategy()
    else:
        raise ValueError(f"Unknown strategy: {strategy_name}")
        
    llm_output_dir = output_dir / "llm_results" / strategy_name
    llm_output_dir.mkdir(parents=True, exist_ok=True)
    
    for part_id, part_data in data.items():
        print(f"Processing {part_id}...")
        
        # Prepare context (mainly for RAG)
        context = {}
        if strategy_name == "rag":
            context['dxf_structure'] = part_data.get('dxf_structure', {})
            
        # Generate prompt
        prompt = strategy.generate_prompt(part_data, context)
        
        # Call LLM
        response = processor.ask_llm(prompt)
        
        # Save Result
        out_file = llm_output_dir / f"{part_id}_annotation.json"
        import json
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(response, f, indent=2)
            
    print(f"✅ LLM processing complete. Results in {llm_output_dir}")

def main():
    parser = argparse.ArgumentParser(description="DXF Interoperability Pipeline")
    parser.add_argument("--subdir", type=str, required=True, help="Subdirectory in 'data' folder (e.g., teknocer)")
    parser.add_argument("--mode", choices=["parse", "llm", "all"], default="all", help="Execution mode")
    parser.add_argument("--strategy", choices=["zero-shot", "few-shot", "rag"], default="zero-shot", help="LLM Strategy")
    
    args = parser.parse_args()
    
    data = None
    output_dir = Config.get_output_dir(args.subdir)
    
    if args.mode in ["parse", "all"]:
        data, output_dir = run_parser_pipeline(args.subdir)
        
    if args.mode in ["llm", "all"]:
        # If skipping parse, load data from previous run? 
        # For now, simplistic approach: 'all' runs both in memory. 
        # If 'llm' only, we'd need to load from files (feature for later).
        if data is None:
             print("Error: 'llm' mode requires data. Run with 'all' or implement loading logic.")
             sys.exit(1)
             
        run_llm_pipeline(data, output_dir, args.strategy)

if __name__ == "__main__":
    main()
