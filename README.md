# Gigapixel Lab

A project exploring lymph-node metastasis detection in whole-slide pathology images.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run these commands from the repository root:

```bash
uv sync --locked
uv run --locked jupyter lab
```

The project uses Python 3.13.18, pinned in `.python-version`. The supported Python range and dependencies are in `pyproject.toml`; `uv.lock` records the resolved package versions. 

`uv sync --locked` downloads the pinned Python version if needed and creates `.venv/` with the locked dependencies, including Jupyter. Keep `.venv/` outside Git and recreate it on each machine. 


Project decisions and findings go in [LOG.md](LOG.md).

Start with [the data-audit notebook](notebooks/01_data_audit.ipynb) and run its cells from top to bottom. It downloads the small CAMELYON17 metadata files and a file listing, then reuses the saved snapshot on later runs. The audit counts labels by hospital and estimates image storage. Read the [audit notes](docs/data_audit.md) for the findings and limitations.

Next, [open one annotated slide](notebooks/02_look_at_slides.ipynb). This notebook downloads one TIFF image (about 875 MB) and its XML annotation, verifies their checksums, and uses OpenSlide to show the resolution levels and a thumbnail with tumor outlines. Later runs reuse the verified files. OpenSlide's Python package and native library are included in the uv dependencies; this runs on the CPU.

Then [compare two slides per hospital](notebooks/02b_compare_hospitals.ipynb). The [fixed inspection sample](manifests/inspection_slides.csv) contains one negative slide and one annotated macro slide from each hospital, with source locations and checksums. The ten TIFFs need about 16.76 GB in total, including the first example. The notebook explains the selection, compares pixel sizes and resolution levels, and shows all five hospitals in one thumbnail grid.

## Research question

**How accurately and efficiently can we identify slides containing lymph-node metastases—and what happens when the slides come from different sites?**

## Datasets

**CAMELYON17 is the primary dataset.** 
- We will start with a small subset of labeled training slides for tumor-present vs. tumor-absent classification.
- Then evaluate generalization across hospitals using custom hospital split.
- Downloaded data in `data/`. 
- We will record selected slide IDs and dataset versions so experiments can be reproduced.

| Dataset | What the dataset contains | Storage |
| --- | --- | --- |
| **CAMELYON17** | 1,000 H&E-stained whole-slide lymph-node images from five medical centers for metastasis analysis. | Approximately **2.3 TB** for the complete original release; need to focus on selected slides first. |
| **CAMELYON16** | 399 whole-slide lymph-node images from two medical centers, with tumor labels and lesion annotations. | Approximately **716 GB** for the complete original release. |
| **CAMELYON17-WILDS** | Prepared **96 × 96-pixel tissue patches** with tumor labels and hospital splits for generalization experiments. These are patches, not full slides. | Approximately **10 GB to download / 15 GB extracted** for the labeled dataset. |


### Sources

- [CAMELYON paper: dataset design and original storage sizes](https://geertlitjens.nl/publication/band-18/band-18.pdf)
- [CAMELYON public downloads and CC0 license](https://registry.opendata.aws/camelyon/)
- [WILDS dataset description](https://wilds.stanford.edu/datasets/#camelyon17) and [download/storage sizes](https://wilds.stanford.edu/get_started/)

## Structure

```text
gigapixel-lab/
├── .python-version # Pinned Python interpreter version
├── LOG.md          # Research questions, decisions, and findings
├── data/           # Local datasets (excluded from Git)
├── docs/           # Analysis plan and report
├── manifests/      # Fixed sample selections and source checksums
├── notebooks/      # Exploration and learning
├── splits/         # Dataset split definitions
├── src/            # Project code as we build it
├── pyproject.toml  # Python version range and dependencies
├── uv.lock         # Resolved dependency versions
└── README.md       # Project overview
```
