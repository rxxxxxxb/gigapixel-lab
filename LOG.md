# Research log

## 2026-10-21 · Step 0: Set up

Goal: I want to explore ML for pathology and will use AI agent to help me research and code. This log will walk through my planning and Thought process from the beginning and what I learn along the way.

Question: How much does slide-classification performance change when the model encounters a hospital it did not see during training?

Expectation: I expect lower AUC when the test hospital is left out of training, with a larger drop for small lesions. I'll test this on CAMELYON17. 

What I did: Created the `uv` project and `.venv`, pinned Python to 3.13.16, and added the data-audit and notebook dependencies. Added `docs/` and `splits/`, plus setup commands in the README.

What I found: The packages import correctly on the Mac, and basic table operations and plotting work. A fresh environment in a separate directory installed from `uv.lock` with `uv sync --locked --offline`. This checks the Mac setup; Linux and GPU support still need their own check when the training dependencies are added.

Decision: Use `uv` with Python 3.13 and a local `.venv`. Let's Keep the dependency versions in Git so I can recreate the setup on another machine.
