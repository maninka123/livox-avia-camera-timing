# Automatic localization: actual-capture comparison

All **10 bags**, **14,281 camera frames**, **4,205 LiDAR clouds**, and **100,920,000 input points** were processed. All ten wheels were localized with camera-guided spatial priors verified by independent LiDAR rotation.

| Bag | Previous LiDAR STD (°) | Automatic LiDAR STD (°) | STD reduction | Target depth (m) |
|---|---:|---:|---:|---:|
| rig_20260828_191635_0.bag | 0.6103 | 0.6546 | -7.3% | 1.897 |
| rig_20260828_191845_0.bag | 0.6045 | 0.4916 | +18.7% | 1.897 |
| rig_20260828_192028_0.bag | 0.5738 | 0.4887 | +14.8% | 1.898 |
| rig_20260828_192202_0.bag | 0.7887 | 0.6578 | +16.6% | 1.896 |
| rig_20260828_192433_0.bag | 0.6272 | 0.6036 | +3.8% | 1.895 |
| rig_20260828_192618_0.bag | 0.6116 | 0.4699 | +23.2% | 1.898 |
| rig_20260828_192752_0.bag | 0.8222 | 0.6740 | +18.0% | 1.900 |
| rig_20260828_192952_0.bag | 0.6711 | 0.5623 | +16.2% | 1.687 |
| rig_20260828_193136_0.bag | 0.6321 | 0.5164 | +18.3% | 1.690 |
| rig_20260828_193309_0.bag | 0.7065 | 0.6742 | +4.6% | 1.686 |

![Per-capture comparison](figures/automatic_comparison.png)

Nine captures improve; one worsens slightly. Median per-bag STD reduction is **16.4%**. These are held-out camera disagreement statistics, not absolute angle accuracy; discovery geometry uses samples across the sequence. Camera estimates remain numerically unchanged.

The combined candidate is **-25.947 ms**, standard error **0.912 ms**, conditional 95% interval **[-28.103, -23.790] ms**, phase residual STD **0.1817°**. The previous result was −25.971 ms. The original H5 timing signatures are **exactly equal** for every bag (maximum absolute difference 0), while relative-angle inference uses the newly localized region. Physical sensor synchronization remains uncalibrated.

The supplied September enclosure-off calibration gives a coarse camera prior on these August captures: the detected/projected centres differ by 30.3–31.9 pixels. This is explicitly flagged in each report. It is not the 0.517 px held-out error measured in the source calibration run.

Software verification covers off-axis/different-depth synthetic rotors, changing-density static scenes, multiple-target ambiguity, missing calibration, an incorrect camera prior, wrong image size, verified-reference fallback and unknown-scene rejection. Synthetic transformations are software checks, not additional hardware ground truth.

Full per-scan detections, models, discovery samples, selection decisions, figures and reports are preserved in each capture folder. Original capture files and previous results were not overwritten.
