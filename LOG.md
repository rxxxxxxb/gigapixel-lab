# Research log

## 2026-10-21 · Step 0: Set up

Goal: I want to explore ML for pathology and will use AI agent to help me research and code. This log will walk through my planning and Thought process from the beginning and what I learn along the way.

Question: How much does slide-classification performance change when the model encounters a hospital it did not see during training?

Expectation: I expect lower AUC when the test hospital is left out of training, with a larger drop for small lesions. I'll test this on CAMELYON17. 

What I did: Created the `uv` project and `.venv`, pinned Python to 3.13.16, and added the data-audit and notebook dependencies. Added `docs/` and `splits/`, plus setup commands in the README.

What I found: The packages import correctly on the Mac, and basic table operations and plotting work. A fresh environment in a separate directory installed from `uv.lock` with `uv sync --locked --offline`. This checks the Mac setup; Linux and GPU support still need their own check when the training dependencies are added.

Decision: Use `uv` with Python 3.13 and a local `.venv`. Let's Keep the dependency versions in Git so I can recreate the setup on another machine.

## 2026-10-22 · Step 1: Check the dataset

Question: What labels are available in the CAMELYON17 AWS copy, how are they spread across hospitals, and how much space would the slides need?

Expectation: The documentation and my draft plan describe 500 labeled training slides across five hospitals. I'll check those figures against the metadata. I expect the mix of labels to differ between hospitals. These expectations come from what I've already read, rather than a first look at the dataset.

What I did: Used the agent to download the README, labels, and checksums, and list the files in the public AWS bucket. Built and ran a notebook to check the records, compare labels by hospital, and add up the image sizes. The downloaded metadata stays in `data/`.

What I found: The CSV has 600 rows: 500 slide labels and 100 artificial patient-group labels. Each hospital has 100 labeled slides, but the label mix differs. Hospital 1 has 23 micro-metastasis slides; hospital 4 has 5. The labeled images need about 1.46 TB in this AWS copy. The full set needs about 2.97 TB. The README and CSV match their published checksums; I haven't checked the image contents yet.

Decision: Keep the four slide labels separate for now and use the published hospital codes. The patient IDs describe artificial groups, so they don't establish that future splits separate real patients. I'll need to account for that when defining the experiment.

Next: Open a small sample of images, check their dimensions and physical pixel sizes, and overlay a tumor annotation on one slide.

## 2026-11-02 · Review the metadata audit

Question: Why does the CSV have 600 rows for 500 labeled images, and what does "artificial patient" mean?

What I learned: There are 500 labels for individual slides and 100 staging labels for groups of five slides. Each group contains real images from the same hospital, assembled from different patients. The organizers used these groups to test staging across several lymph nodes and make the mix of stages more comparable between hospitals. The ZIP names in the CSV identify groups; our saved AWS file list contains individual TIFF images and no ZIP archives.

What I changed: Edited the notebook explanations and updated the audit notes. I'll use "slide group" in the explanations and define the official term once. 

