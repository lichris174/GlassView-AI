"""Training-side code for the sensitive-region detector (data, splits, training, eval).

Kept separate from ``glassview_ai`` (the app backend) so the app never imports
training dependencies. See docs/DEVLOG.md for the plan and docs/LABELING_GUIDE.md
for how the dataset is collected and labeled.
"""
