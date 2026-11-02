# CAMELYON17 metadata audit

Original audit: 2026-10-22. Explanations reviewed: 2026-11-02. The [notebook](../notebooks/01_data_audit.ipynb) contains the code, tables, and plots.

## Scope

The audit read every row of the AWS copy's `stages.csv` and all 1,157 objects returned by the paginated listing under `CAMELYON17/`. It also read the dataset README and checksum list. The downloaded files and listing total about 228 KiB. No images, masks, or XML contents were downloaded.

The expectation of 500 labeled training slides came from the documentation and draft plan before this audit. These results describe this metadata snapshot, rather than a new statistical test of the research hypothesis.

## What is labeled?

The CSV contains 600 records: 500 labels for individual slides and 100 staging labels for slide groups. Each group has five slides and one additional row for the group's staging label. All labeled slides have matching image files in the listing, and the slide and group hospital codes agree. There are no missing cells, duplicate rows, or duplicate identifiers in the label table.

A slide group is a set of five real lymph-node slide images from the same hospital, assembled from different patients. The organizers call it an "artificial patient." They created these groups to test staging across several lymph nodes and obtain a more comparable mix of staging categories between hospitals. Using five slides per group also limited the dataset size. The [challenge paper, section II-C](https://geertlitjens.nl/publication/band-18/band-18.pdf), explains these choices.

The ZIP names in the label CSV identify the groups. Our saved AWS file list contains individual TIFF images and no ZIP archives.

| Hospital code | Negative | ITC | Micro | Macro | Total |
|---|---:|---:|---:|---:|---:|
| 0 | 64 | 11 | 10 | 15 | 100 |
| 1 | 58 | 7 | 23 | 12 | 100 |
| 2 | 75 | 2 | 8 | 15 | 100 |
| 3 | 60 | 8 | 13 | 19 | 100 |
| 4 | 61 | 8 | 5 | 26 | 100 |
| Total | 318 | 36 | 59 | 87 | 500 |

The four categories remain separate. We have not decided how to handle isolated tumor cells (ITC) in a binary target. These dataset counts do not estimate clinical prevalence.

The listing contains 1,000 whole-slide images. The other 500 have no labels in this CSV; they are not treated as negative. This audit does not establish which labels might be available in other releases.

There are 50 XML annotation files, ten per hospital, and 100 mask files. These counts establish file availability only. The challenge documentation says ITCs were not annotated exhaustively.

## Storage

| Image files | Count | Stored bytes | Decimal TB |
|---|---:|---:|---:|
| Labeled slides | 500 | 1,461,349,695,544 | 1.461 |
| All slides | 1,000 | 2,973,774,738,350 | 2.974 |

These totals cover full TIFF objects in the AWS copy, excluding masks, tiles, features, and model outputs. They are not decoded memory requirements. The labeled files have a mean size of 2.923 GB and median of 2.759 GB; the largest is 8.424 GB. All files remain in the totals, including the eight above the upper IQR size fence.

## Checks and limits

The downloaded README and label CSV match their published MD5 hashes. All 1,000 slide-image objects have expected MD5 hashes in the publisher's list, but their contents have not been downloaded or verified.

Keeping a slide group in one fold does not by itself establish independence between real patients. The group IDs do not establish which slides came from the same person. The [official evaluation description](https://camelyon17.grand-challenge.org/Evaluation/) explains this construction. The split design still needs to account for that limitation.

We kept hospital codes 0 to 4 because the order of names in the README does not establish their mapping. We have not inspected pixel dimensions, physical pixel sizes, pyramid levels, staining, or image integrity. That is the next step. No model splits or fitted preprocessing were created in this audit.

## Reproduce the audit

Run `uv sync --locked`, then `uv run --locked jupyter lab notebooks/01_data_audit.ipynb` and run all cells. The first cell fetches metadata when it is absent. The downloader can also run separately with `uv run --locked python src/fetch_camelyon17_metadata.py`.

Raw files and retrieval metadata are under `data/raw/camelyon17/`. The provenance file records SHA-256 hashes and the retrieval timestamp, `2026-10-21T23:43:20.479989+00:00` (2026-10-22 in Berlin). Subsequent runs verify and reuse this snapshot offline. A new download may differ if the public bucket changes.

Derived inventories, aggregate tables, PNG/SVG plots, software versions, and output hashes are under `data/derived/camelyon17/`. These data folders are excluded from Git. The notebook bounds CSV input to 8 MiB and 20,000 rows per file; both files were read in full within those limits. It rejects malformed rows and unknown label categories, without deleting records or imputing labels.

## Sources and software

- [CAMELYON on AWS Open Data](https://registry.opendata.aws/camelyon/), accessed 2026-10-22; the dataset's `README.md`, `stages.csv`, and `checksums.md5`; and the saved object listing.
- [CAMELYON17 data documentation](https://camelyon17.grand-challenge.org/Data/).
- Litjens et al. (2018). [1399 H&E-stained sentinel lymph node sections of breast cancer patients: the CAMELYON dataset](https://doi.org/10.1093/gigascience/giy065).
- Software used for the original audit: Python 3.13.16, pandas 3.0.6, NumPy 2.5.4, boto3 1.43.116, and Matplotlib 3.11.2. Exact dependency versions are in `uv.lock`.
- EDA workflow and local profiling: `exploratory-data-analysis` skill 1.4. Kassis, T., Agarwal, V., He, Y., Patel, D., and Brueckner, A. M. (2026). [Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents](https://doi.org/10.48550/arXiv.2609.00065).
