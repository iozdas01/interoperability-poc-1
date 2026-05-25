# interoperability-poc-1

Proof-of-concept code for my MPhil dissertation at the University of Cambridge (ISMM, 2025):

> **The Interoperability Crisis: Investigating LLMs for Semantic Integration of Manufacturing Software**
> Izgin Ozdas · Supervisor: Dr. Sam Brooks · Second marker: Thomas Bohné

It implements a dual-LLM pipeline that bridges the semantic gap between unstructured engineering documents (PDF, QIF, CSV) and native CAD/CAM file formats (DXF, STEP). The system extracts production-critical metadata — material, thickness, part ID — and injects it back into the original CAD file so the digital thread between design and manufacturing is preserved without manual re-entry.

## Problem

In real factories, geometry and metadata routinely arrive in different files. Operators read material and thickness from a PDF and retype them into CAM software, breaking the digital thread. Existing interoperability solutions (vendor APIs, middleware, ontologies) either stop at syntactic integration or require brittle, manually maintained mappings. The thesis frames LLMs as adaptive semantic intermediaries and tests how far that goes on real industrial data.

## Architecture

A two-stage LLM pipeline (Figure 8 in the thesis):

1. **Parser layer** — deterministic parsers for STEP (`pythonocc-core`), DXF (`ezdxf`), QIF, and PDF (`pdfplumber` + `pdf2image`) normalise every input into a single JSON schema per part.
2. **LLM 1 — Extraction** reads the unstructured sources and emits a fixed-schema JSON payload with material, thickness, part ID, etc. Multilingual and layout-tolerant.
3. **LLM 2 — Annotation** consumes the structured metadata plus the target file's own schema trace and produces patch instructions that are applied directly to the native DXF or STEP file.
4. **Evaluator** scores each annotated file against a hand-built ground truth (precision / recall / F1) and verifies structural validity of the output.

Four prompting strategies are implemented and evaluated for each target format:

| Strategy        | DXF class                | STEP class                   |
| --------------- | ------------------------ | ---------------------------- |
| Zero-shot       | `ZeroShotStrategy`       | `StepZeroShotStrategy`       |
| Zero-shot + RAG | `ZeroShotRAGStrategy`    | `StepZeroShotRAGStrategy`    |
| Few-shot        | `FewShotStrategy`        | `StepFewShotStrategy`        |
| Few-shot + RAG  | `FewShotRAGStrategy`     | `StepFewShotRAGStrategy`     |

RAG variants ground the prompt in the target file's existing structure (header fields, entity IDs) to disambiguate where metadata should land.

## Case studies

- **Case 1 — Teknocer (Turkey), laser cutting, DXF.** Customer PDFs hold material and thickness; DXFs hold only geometry. Operators retype into CypCut CAM.
- **Case 2 — Universal Wolf (UK), sheet-metal fabrication, STEP.** Inventor-to-TechZone handoff loses the material link in AP-242 STEP files.

## Results

| Experiment           | Best strategy   | Average F1 | Max F1 |
| -------------------- | --------------- | ---------- | ------ |
| Case 1 — DXF (20 parts) | Zero-shot + RAG | **1.00**   | 1.00   |
| Case 2 — STEP (40 parts) | Few-shot + RAG  | **0.743**  | 0.91   |

Zero-shot baselines collapsed on the STEP case (F1 ≈ 0.04), confirming that prompt tuning alone is insufficient for heterogeneous engineering schemas and that retrieval-grounded context is the dominant factor.

A separate upstream-integration study tested the annotated outputs against commercial software via vendor docs and direct correspondence: **3/10 CAM tools fully consumed the DXF annotations, and 5/12 CAD tools fully preserved AP-242 STEP metadata** — ecosystem openness and standards alignment were the deciding factors.

## Repository layout

```
parsers/         STEP, DXF, QIF, PDF parsers → unified JSON
llm/
  processor.py   OpenAI client + retry / JSON-mode wrapper
  strategies.py  Zero-shot, few-shot, RAG variants for DXF and STEP
  annotator.py   Applies LLM-generated patches to native files
  evaluator.py   Metadata F1 + structural validity checks
config.py        Paths, parser tolerances, ignored dirs
main.py          CLI entry point — runs parse / llm / full pipeline
data/teknocer/   Sample DXF + PDF + STEP + annotated ground truth
execute/         Pipeline outputs (parsed JSON, LLM results, annotated files)
```

## Running it

Conda is recommended — `pythonocc-core` does not install cleanly through pip.

```bash
conda env create -f environment.yaml
conda activate interoperability-env
cp .env.example .env   # set OPENAI_API_KEY and POPPLER_PATH
```

End-to-end run on the bundled Teknocer sample:

```bash
python main.py --subdir teknocer --mode all --strategy zero-shot-rag --target-format dxf
```

Useful flags:

- `--mode {parse,llm,all}` — parse only, LLM only, or full pipeline
- `--strategy {zero-shot,zero-shot-rag,few-shot,few-shot-rag}`
- `--target-format {auto,dxf,step}` — `auto` picks based on the subdirectory name

Outputs land in `execute/parsed-results/<subdir>/` (per-part JSON) and `execute/parsed-results/<subdir>/llm_results/<strategy>/` (annotated CAD files + evaluation reports).

## Contributions

1. A TRL-based taxonomy for evaluating LLM-driven interoperability systems by prompting strategy and mediation type (covered in the dissertation literature review).
2. A modular, file-aware dual-LLM architecture for semantic alignment in native engineering file formats — this repository.

While the immediate target is digital manufacturing, the approach generalises to any domain that needs file-level semantic reconciliation across fragmented tooling.

## Status

Research code, not a product. The pipeline is reproducible on the bundled Teknocer sample; the full Universal Wolf STEP dataset is omitted because the source files are confidential.
