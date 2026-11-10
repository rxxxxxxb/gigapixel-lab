# Research log

## 2026-10-21 · Step 0: Set up

Goal: I want to explore ML for pathology and will use AI agent to help me research and code. This log will walk through my planning and Thought process from the beginning and what I learn along the way.

Question: How much does slide-classification performance change when the model encounters a hospital it did not see during training?

Expectation: I expect lower AUC when the test hospital is left out of training, with a larger drop for small lesions. I'll test this on CAMELYON17. 

What I did: Created the `uv` project and `.venv`, pinned Python to 3.13.16, and added the data-audit and notebook dependencies. Added `docs/` and `splits/`, plus setup commands in the README.

What I found: The packages import correctly on the Mac, and basic table operations and plotting work. A fresh environment in a separate directory installed from `uv.lock` with `uv sync --locked --offline`. This checks the Mac setup; Linux and GPU support still need their own check when the training dependencies are added.

Decision: Use `uv` with Python 3.13 and a local `.venv`. Let's Keep the dependency versions in Git so I can recreate the setup on another machine.

---

## 2026-10-22 · Step 1: Check the dataset

Question: What labels are available in the CAMELYON17 AWS copy, how are they spread across hospitals, and how much space would the slides need?

Expectation: The documentation and my draft plan describe 500 labeled training slides across five hospitals. I'll check those figures against the metadata. I expect the mix of labels to differ between hospitals. These expectations come from what I've already read, rather than a first look at the dataset.

What I did: Used the agent to download the README, labels, and checksums, and list the files in the public AWS bucket. Built and ran a notebook to check the records, compare labels by hospital, and add up the image sizes. The downloaded metadata stays in `data/`.

What I found: The CSV has 600 rows: 500 slide labels and 100 artificial patient-group labels. Each hospital has 100 labeled slides, but the label mix differs. Hospital 1 has 23 micro-metastasis slides; hospital 4 has 5. The labeled images need about 1.46 TB in this AWS copy. The full set needs about 2.97 TB. The README and CSV match their published checksums; I haven't checked the image contents yet.

Decision: Keep the four slide labels separate for now and use the published hospital codes. The patient IDs describe artificial groups, so they don't establish that future splits separate real patients. I'll need to account for that when defining the experiment.

Next: Open a small sample of images, check their dimensions and physical pixel sizes, and overlay a tumor annotation on one slide.

---

## 2026-11-02 · Review the metadata audit

Question: Why does the CSV have 600 rows for 500 labeled images, and what does "artificial patient" mean?

What I learned: There are 500 labels for individual slides and 100 staging labels for groups of five slides. Each group contains real images from the same hospital, assembled from different patients. The organizers used these groups to test staging across several lymph nodes and make the mix of stages more comparable between hospitals. The ZIP names in the CSV identify groups; our saved AWS file list contains individual TIFF images and no ZIP archives.

What I changed: Edited the notebook explanations and updated the audit notes. I'll use "slide group" in the explanations and define the official term once. 

---

## 2026-11-03 · Step 2: Open one annotated slide

Question: Since I do not have enough space  on my Mac for all the WSI, lets check if I can open a whole-slide image, read its resolution information, and draw the supplied tumor outline in the right place?

Expectation: The file should contain several resolution levels. I'll check whether it records the physical pixel size instead of assuming that the metadata is complete.

Selection: Start with `patient_092_node_1.tif` from hospital 4. At about 875 MB, it is the smallest slide in the saved inventory with a macrometastasis label and an XML annotation. I chose it to check the reading and plotting code. It is not a representative sample of the dataset.

What I did: Used OpenSlide, downloaded the TIFF and XML, and build a notebook for reading the slide metadata and displaying the annotation. Both files match their published MD5 checksums. All notebook code cells ran successfully on the Mac using the saved files. The agent checked the rendered thumbnail and overlay.

What I found: The image is 184,320 by 93,696 pixels, about 17.27 gigapixels. It has ten resolution levels and records 0.25 micrometers per pixel in both directions. The objective magnification field is missing. The XML contains four tumor polygons, all their coordinates fall within the image. The main outline is visible on the thumbnail, while the smaller outlines are difficult to see at that scale.

Environment:  Added the OpenSlide packages and Pillow to the project dependencies and updated the lockfile. Updated uv from 0.12.1 to 0.13.7 so it could download Python 3.13.18, rebuilt `.venv`, and set `python-preference = "only-managed"` in `pyproject.toml`. The README now explains this setup.  The agent confirmed that all 106 installed package versions match the previous environment and that `uv.lock` is unchanged. All six code cells in the slide-inspection notebook ran successfully with the new environment. The executed copy is saved under `data/derived/environment_check/`.

Decision: Record the physical pixel size from the file and leave missing magnification metadata unset. Keep the downloaded image and generated inspection files  `data/`.

Next: Work through this example, then inspect two slides per hospital to compare their resolution metadata and thumbnails.

---

## 2026-11-08 · Step 2: Compare slides from all five hospitals

Question: Let's read the  slides from every hospital, and check if their pixel sizes or resolution levels differ?

Expectation: The first slide opened at 0.25 micrometers per pixel and had ten resolution levels. I'll check the other slides before deciding how to choose a common resolution for tiles.

**Selection and reasoning:** 

- Use one negative slide and one annotated macrometastasis slide per hospital. This gives each hospital the same two label categories and provides tumor outlines for checking coordinates. 
- Within each category, choose the smallest eligible file, with the filename breaking any tie, to keep the download manageable. 
- The ten TIFFs total 16.76 GB, including the slide already downloaded. 
- This small selection can reveal reading problems and missing metadata; it cannot establish typical hospital appearance or model performance.

**Reproducibility**: Save the ten slide IDs, hospital codes, labels, source keys, sizes, and published checksums in `manifests/inspection_slides.csv`. Check those details against the saved metadata before downloading each slide.

**What I did:**  

- Extended the downloader to use this manifest and ran `02b_compare_hospitals.ipynb` on the Mac. 
- All ten TIFFs and five XML files match their published MD5 checksums. 
- All code cells ran successfully, and the agent checked them. 
- The five XMLs contain 99 tumor polygons. All coordinates fall within their images. Small outlines still need closer views.

**What I found:** 

- The selected slides from hospitals 0, 1, and 3 record about 0.243094 micrometers per pixel and have nine resolution levels. 
- Hospital 2 records 0.226316 in X and 0.226321 in Y, with eight levels. 
- Hospital 4 records 0.25 in both directions and has ten levels. 
- Every file provides physical pixel sizes, but none provides objective magnification or an embedded color profile.

**Reading notes:** 

- The examples from hospitals 0, 1, and 3 have large black areas around tissue; those from hospitals 2 and 4 have pale backgrounds. 
- The tissue mask will need to exclude both. These are observations from two selected slides per hospital, not estimates of how common these appearances are.

**Decision:** Start the tiling pilot at 0.5 micrometers per pixel, using each file's X and Y pixel sizes to resample. This target is close to level 1 in all ten files. At level 1 without resampling, a 256-pixel-wide crop would span about 115.9 micrometers in the hospital 2 examples and 128 micrometers in hospital 4.

**Next:** Build a tissue mask and a small tile grid on this same set, then inspect both over the thumbnails.
