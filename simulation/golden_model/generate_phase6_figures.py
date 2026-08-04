"""Generate deterministic Phase-6 manuscript figures and candidate tables."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.hashsalt"] = "rdmr-pli-phase6-20260803"

import matplotlib.pyplot as plt
from matplotlib import colors as mpl_colors
from matplotlib import patches
import numpy as np
import pandas as pd
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs" / "phase6_figures"
FIG_DIR = OUT_DIR / "figures"
TABLE_DIR = OUT_DIR / "tables"
PHASE4_DIR = ROOT / "outputs" / "phase4_host"
PHASE5_DIR = ROOT / "outputs" / "phase5_physical_core"
PHASE6_STATS = ROOT / "outputs" / "phase6_statistics"
PHASE3_DIR = ROOT / "outputs" / "phase3_tuning"

PROTOCOL = (
    ROOT / "paper_workspace" / "scope"
    / "experiment-protocol__rdmr-pli__cssp-journal__candidate__v0.3.0.md"
)
NONPUBLIC_EI_DRAFT_SHA256 = (
    "629A01139433FBA0E07191C64263D02EF7EDEE8CBFE237C9D1419FE630BDF287"
)
METRICS_CSV = PHASE4_DIR / "phase4_run_metrics.csv"
HOLM_CSV = PHASE6_STATS / "phase6_holm_by_trajectory.csv"
STATS_JSON = PHASE6_STATS / "phase6_paired_statistics.json"
ALGORITHM_CSV = PHASE6_STATS / "phase6_main_algorithm_summary.csv"
ABLATION_CSV = PHASE6_STATS / "phase6_ablation_summary.csv"
PHYSICAL_MATRIX_CSV = PHASE5_DIR / "phase5_physical_matrix_summary.csv"
PHYSICAL_RESOURCE_CSV = PHASE5_DIR / "phase5_physical_resource_summary.csv"
CONSISTENCY_CSV = PHASE5_DIR / "phase5_three_level_consistency.csv"
PHOTO_MANIFEST = PHASE5_DIR / "phase5_physical_photo_evidence_manifest.json"
PHOTO_CLOSEUP = PHASE5_DIR / "photos" / "PHASE5_PHYSICAL_PLATFORM_CLOSEUP_20260802.jpg"
PHOTO_OVERVIEW = PHASE5_DIR / "photos" / "PHASE5_PHYSICAL_WIRING_OVERVIEW_20260802.jpg"
LOG_DIR = PHASE5_DIR / "logs"

TABLE1_CSV = TABLE_DIR / "table1_protocol_and_data_partition.csv"
TABLE2_CSV = TABLE_DIR / "table2_four_algorithm_main_results.csv"
TABLE3_CSV = TABLE_DIR / "table3_stm32_cycles_flash_ram.csv"
MANIFEST_JSON = OUT_DIR / "phase6_figure_table_manifest.json"

ALGORITHM_NAMES = {
    0: "A0",
    1: "A1",
    2: "A2",
    3: "A3",
}
ALGORITHM_COLORS = {
    "A0": "#7f7f7f",
    "A1": "#1f77b4",
    "A2": "#d62728",
    "A3": "#2ca02c",
}
ALGORITHM_MARKERS = {"A0": "o", "A1": "s", "A2": "^", "A3": "D"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_figure(fig: plt.Figure, stem: str) -> list[Path]:
    png = FIG_DIR / f"{stem}.png"
    svg = FIG_DIR / f"{stem}.svg"
    fig.savefig(
        png,
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
        metadata={"Software": "Matplotlib; run_phase6_figures; 2026-08-03"},
    )
    fig.savefig(
        svg,
        bbox_inches="tight",
        facecolor="white",
        metadata={"Creator": "Matplotlib run_phase6_figures", "Date": "2026-08-03"},
    )
    plt.close(fig)
    return [png, svg]


def draw_box(ax: plt.Axes, xy: tuple[float, float], width: float, height: float,
             text: str, color: str) -> None:
    box = patches.FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.02",
        linewidth=1.3,
        edgecolor=color,
        facecolor=mpl_colors.to_rgba(color, 0.10),
    )
    ax.add_patch(box)
    ax.text(xy[0] + width / 2, xy[1] + height / 2, text,
            ha="center", va="center", fontsize=9)


def draw_arrow(ax: plt.Axes, start: tuple[float, float], end: tuple[float, float],
               color: str = "#333333", style: str = "-",
               connectionstyle: str = "arc3") -> None:
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops={"arrowstyle": "->", "lw": 1.2, "color": color,
                    "linestyle": style, "connectionstyle": connectionstyle},
    )


def figure1_scheduler() -> tuple[list[Path], dict[str, Any]]:
    fig, ax = plt.subplots(figsize=(11.5, 5.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    draw_box(ax, (0.04, 0.60), 0.12, 0.14, "Input\nx[n]", "#4c78a8")
    draw_box(ax, (0.25, 0.60), 0.18, 0.14, "Adaptive\ncanceller", "#4c78a8")
    draw_box(ax, (0.52, 0.60), 0.16, 0.14, "Residual\ne[n]", "#4c78a8")
    draw_box(ax, (0.78, 0.60), 0.16, 0.14, "Filtered output\ny[n]", "#4c78a8")
    draw_arrow(ax, (0.16, 0.67), (0.25, 0.67))
    draw_arrow(ax, (0.43, 0.67), (0.52, 0.67))
    draw_arrow(ax, (0.68, 0.67), (0.78, 0.67))

    draw_box(ax, (0.22, 0.22), 0.18, 0.14, "Frequency tracker\nPLL-like update", "#e45756")
    draw_box(ax, (0.47, 0.22), 0.17, 0.14, "Quadrature\nreference", "#f2cf5b")
    draw_arrow(ax, (0.40, 0.29), (0.47, 0.29))
    draw_arrow(ax, (0.555, 0.36), (0.34, 0.60), color="#7a7a7a")

    draw_box(ax, (0.70, 0.20), 0.24, 0.18,
             "Residual-driven scheduler\nFAST / MID / SLOW\n1 / 3 / 12 blocks",
             "#54a24b")
    draw_arrow(ax, (0.60, 0.60), (0.79, 0.38), color="#54a24b")
    draw_arrow(
        ax,
        (0.70, 0.24),
        (0.40, 0.24),
        color="#54a24b",
        connectionstyle="arc3,rad=-0.42",
    )

    ax.text(0.5, 0.94, "Residual-driven multirate PLI cancellation (A3)",
            ha="center", va="center", fontsize=14, fontweight="bold")
    ax.text(
        0.5,
        0.06,
        "A2 updates the tracker every block; A3 schedules tracker updates from the residual state.\n"
        "A0/A1 are fixed-frequency explanatory baselines.",
        ha="center",
        va="center",
        fontsize=9,
        color="#444444",
    )
    files = save_figure(fig, "fig1_algorithm_and_scheduler")
    return files, {
        "figure_id": "Fig1",
        "function": "Explain the A3 signal path and FAST/MID/SLOW scheduler.",
        "sources": ["frozen protocol v0.3.0", "frozen Rev15 implementation"],
        "transformation": "Original vector diagram generated from the implementation structure.",
        "rights_state": "ORIGINAL_PROJECT_GENERATED",
        "first_citation": "Methods: proposed residual-driven multirate scheduler",
    }


def figure2_tracking_waveforms() -> tuple[list[Path], dict[str, Any]]:
    trajectories = ["F1", "F2", "F5"]
    fig, axes = plt.subplots(2, 3, figsize=(13.0, 6.8), sharex="row")
    time = np.arange(8000, dtype=np.float64) / 1000.0
    excerpt = slice(6000, 6401)
    for column, trajectory in enumerate(trajectories):
        archive = PHASE4_DIR / "batches" / f"main_{trajectory}_P050_Z1_N0.npz"
        with np.load(archive) as data:
            true_frequency = data["true_frequency"][0]
            estimates = data["estimated_frequency"][:, 0, :]
            clean = data["clean"][0]
            outputs = data["output"][:, 0, :]
        top = axes[0, column]
        top.plot(time, true_frequency, color="#111111", lw=1.6, label="True")
        top.plot(time, estimates[2], color=ALGORITHM_COLORS["A2"], lw=1.0,
                 alpha=0.85, label="A2")
        top.plot(time, estimates[3], color=ALGORITHM_COLORS["A3"], lw=1.0,
                 alpha=0.85, label="A3")
        top.set_title(trajectory, fontweight="bold")
        top.grid(alpha=0.25)
        if column == 0:
            top.set_ylabel("Frequency (Hz)")
            top.legend(frameon=False, ncol=3, fontsize=8, loc="upper left")

        bottom = axes[1, column]
        excerpt_time = time[excerpt]
        bottom.plot(excerpt_time, clean[excerpt], color="#111111", lw=1.2,
                    label="Clean")
        bottom.plot(excerpt_time, outputs[2, excerpt],
                    color=ALGORITHM_COLORS["A2"], lw=0.9, alpha=0.85, label="A2")
        bottom.plot(excerpt_time, outputs[3, excerpt],
                    color=ALGORITHM_COLORS["A3"], lw=0.9, alpha=0.85, label="A3")
        bottom.set_xlabel("Time (s)")
        bottom.grid(alpha=0.25)
        if column == 0:
            bottom.set_ylabel("Output amplitude")
            bottom.legend(frameon=False, ncol=3, fontsize=8, loc="upper left")

    fig.suptitle(
        "Frozen representative traces: PLI amplitude 0.5, 20 dB noise, seed 1000",
        fontsize=12,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    files = save_figure(fig, "fig2_frequency_tracking_and_output_waveforms")
    return files, {
        "figure_id": "Fig2",
        "function": "Show representative tracking and output traces for F1/F2/F5.",
        "sources": [
            "outputs/phase4_host/batches/main_F1_P050_Z1_N0.npz",
            "outputs/phase4_host/batches/main_F2_P050_Z1_N0.npz",
            "outputs/phase4_host/batches/main_F5_P050_Z1_N0.npz",
        ],
        "transformation": (
            "Predeclared first frozen seed (1000), PLI=0.5, noise=20 dB; full 8 s "
            "frequency trace and fixed 6.0-6.4 s output excerpt."
        ),
        "rights_state": "ORIGINAL_PROJECT_DATA",
        "first_citation": "Results: representative dynamic trajectories",
    }


def figure3_snr_ci() -> tuple[list[Path], dict[str, Any]]:
    rows = pd.read_csv(HOLM_CSV)
    stats = load_json(STATS_JSON)
    overall = stats["primary_a3_vs_a2"]["output_snr"]
    labels = ["Overall", *rows["trajectory"].tolist()]
    means = np.asarray([overall["difference_mean"], *rows["snr_difference_mean_db"]])
    lower = np.asarray([
        overall["bootstrap_ci95_mean_lower"],
        *rows["bootstrap_ci95_mean_lower_db"],
    ])
    upper = np.asarray([
        overall["bootstrap_ci95_mean_upper"],
        *rows["bootstrap_ci95_mean_upper_db"],
    ])
    y = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8.8, 5.5))
    ax.errorbar(
        means,
        y,
        xerr=np.vstack([means - lower, upper - means]),
        fmt="o",
        color="#2b6f9f",
        ecolor="#2b6f9f",
        capsize=3,
        lw=1.4,
    )
    ax.axvline(0.0, color="#444444", lw=1.0, label="Equality")
    ax.axvline(-0.5, color="#d62728", lw=1.2, ls="--",
               label="Noninferiority margin (-0.5 dB)")
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel("Output SNR difference, A3 - A2 (dB)")
    ax.set_title("Paired mean differences with 95% bootstrap CIs", fontweight="bold")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    files = save_figure(fig, "fig3_snr_difference_bootstrap_ci")
    return files, {
        "figure_id": "Fig3",
        "function": "Report overall and trajectory-level A3-A2 output-SNR differences.",
        "sources": [str(HOLM_CSV.relative_to(ROOT)), str(STATS_JSON.relative_to(ROOT))],
        "transformation": "Forest plot of deterministic 20,000-resample paired bootstrap CIs.",
        "rights_state": "ORIGINAL_PROJECT_DATA",
        "first_citation": "Results: paired noninferiority analysis",
    }


def figure4_pareto() -> tuple[list[Path], dict[str, Any]]:
    physical = pd.read_csv(PHYSICAL_MATRIX_CSV)
    consistency = pd.read_csv(CONSISTENCY_CSV)[
        ["scenario_id", "physical_output_snr_db"]
    ]
    data = physical.merge(consistency, on="scenario_id", how="left")
    fig, ax = plt.subplots(figsize=(9.2, 6.0))
    norm = mpl_colors.Normalize(
        vmin=float(data["physical_output_snr_db"].min()),
        vmax=float(data["physical_output_snr_db"].max()),
    )
    cmap = plt.get_cmap("viridis")
    for algorithm in ["A0", "A1", "A2", "A3"]:
        subset = data[data["algorithm"] == algorithm]
        ax.scatter(
            subset["final_tracker_calls"],
            subset["cycles_mean"],
            c=subset["physical_output_snr_db"],
            cmap=cmap,
            norm=norm,
            marker=ALGORITHM_MARKERS[algorithm],
            s=85,
            edgecolor="black",
            linewidth=0.6,
            label=algorithm,
            zorder=3,
        )
        if algorithm != "A2":
            offsets = {
                501: (6, 3),
                502: (6, 3),
                504: (-30, 6),
                506: (7, 14),
                508: (7, 4),
                510: (7, -9),
                512: (7, 4),
            }
            for _, row in subset.iterrows():
                scenario_id = int(row["scenario_id"])
                ax.annotate(
                    f"S{scenario_id}",
                    (row["final_tracker_calls"], row["cycles_mean"]),
                    xytext=offsets.get(scenario_id, (5, 5)),
                    textcoords="offset points",
                    fontsize=7,
                )
    a2_subset = data[data["algorithm"] == "A2"]
    ax.annotate(
        "A2: S503/S505/S507/S509/S511",
        (float(a2_subset["final_tracker_calls"].mean()),
         float(a2_subset["cycles_mean"].max())),
        xytext=(-155, 12),
        textcoords="offset points",
        arrowprops={"arrowstyle": "->", "lw": 0.8, "color": "#444444"},
        fontsize=7,
        ha="left",
    )
    ax.axhline(72_000, color="#d62728", ls="--", lw=1.2,
               label="72,000-cycle mean reference")
    ax.set_yscale("log")
    ax.set_xlabel("Tracker calls per 8,000-sample run")
    ax.set_ylabel("Physical mean cycles per sample (log scale)")
    ax.set_title("Physical performance-overhead landscape", fontweight="bold")
    ax.grid(alpha=0.25, which="both")
    handles, labels = ax.get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    ax.legend(unique.values(), unique.keys(), frameon=False, fontsize=8, loc="upper left")
    scalar = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    scalar.set_array([])
    colorbar = fig.colorbar(scalar, ax=ax, pad=0.02)
    colorbar.set_label("Physical output SNR (dB)")
    ax.text(
        0.99,
        0.02,
        "Hard real-time gate uses block maxima, not scenario means.",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color="#555555",
    )
    files = save_figure(fig, "fig4_snr_tracker_calls_cycles_pareto")
    return files, {
        "figure_id": "Fig4",
        "function": "Jointly display physical output SNR, tracker calls, and mean cycles.",
        "sources": [
            str(PHYSICAL_MATRIX_CSV.relative_to(ROOT)),
            str(CONSISTENCY_CSV.relative_to(ROOT)),
        ],
        "transformation": "Scenario-level scatter; log cycle axis; color encodes physical output SNR.",
        "rights_state": "ORIGINAL_PROJECT_DATA",
        "first_citation": "Results: implementation performance-overhead tradeoff",
    }


def figure5_ablation() -> tuple[list[Path], dict[str, Any]]:
    data = pd.read_csv(ABLATION_CSV)
    families = [
        ("state_intervals", "FAST/MID/SLOW interval"),
        ("residual_new_weight", "Residual new-value weight"),
        ("threshold_scale", "Threshold scale"),
        ("block_size_samples", "Block size (samples)"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 7.5))
    legend_handles = None
    legend_labels = None
    for ax, (family, title) in zip(axes.flat, families):
        subset = data[data["family"] == family].reset_index(drop=True)
        x = np.arange(len(subset))
        snr = subset["mean_paired_snr_difference_db"].to_numpy(float)
        calls = 100.0 * subset["median_tracker_calls_reduction_fraction"].to_numpy(float)
        line1 = ax.plot(x, snr, "o-", color="#2b6f9f", lw=1.5,
                        label="Mean SNR difference")
        ax.axhline(-0.5, color="#d62728", ls="--", lw=1.0,
                   label="-0.5 dB margin")
        ax.set_ylabel("A3 - A2 SNR (dB)", color="#2b6f9f")
        ax.tick_params(axis="y", labelcolor="#2b6f9f")
        ax.set_xticks(x, subset["level"].astype(str).tolist())
        ax.set_title(title, fontweight="bold", fontsize=10)
        ax.grid(alpha=0.20)
        twin = ax.twinx()
        line2 = twin.plot(x, calls, "s-", color="#2ca02c", lw=1.4,
                          label="Median call reduction")
        twin.set_ylabel("Tracker-call reduction (%)", color="#2ca02c")
        twin.tick_params(axis="y", labelcolor="#2ca02c")
        selected = np.flatnonzero(subset["selected"].astype(bool).to_numpy())
        if selected.size:
            index = int(selected[0])
            ax.scatter(index, snr[index], marker="*", s=180, color="#ffbf00",
                       edgecolor="black", zorder=5, label="Selected")
        if legend_handles is None:
            h1, l1 = ax.get_legend_handles_labels()
            h2, l2 = twin.get_legend_handles_labels()
            legend_handles, legend_labels = h1 + h2, l1 + l2
    fig.legend(legend_handles, legend_labels, loc="lower center", ncol=4,
               frameon=False, fontsize=8)
    fig.suptitle("One-factor-at-a-time validation-set ablation", fontweight="bold")
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    files = save_figure(fig, "fig5_ablation_tradeoffs")
    return files, {
        "figure_id": "Fig5",
        "function": "Show SNR/call tradeoffs across the four ablation families.",
        "sources": [str(ABLATION_CSV.relative_to(ROOT))],
        "transformation": "One-factor-at-a-time validation-set summaries; selected level highlighted.",
        "rights_state": "ORIGINAL_PROJECT_DATA",
        "first_citation": "Results: ablation and parameter freeze",
    }


def parse_physical_cycles() -> dict[str, list[int]]:
    values: dict[str, list[int]] = {name: [] for name in ALGORITHM_NAMES.values()}
    for path in sorted(LOG_DIR.glob("*.txt")):
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        header_index = next(
            index for index, line in enumerate(lines)
            if line.startswith("run_id,scenario_id,")
        )
        numeric = [line for line in lines[header_index + 1:] if line[:1].isdigit()]
        rows = list(csv.DictReader([lines[header_index], *numeric]))
        for row in rows:
            algorithm = ALGORITHM_NAMES[int(row["algorithm"])]
            cycle = int(row["cycles"])
            if cycle > 0:
                values[algorithm].append(cycle)
    return values


def figure6_photos_cycles() -> tuple[list[Path], dict[str, Any]]:
    cycles = parse_physical_cycles()
    closeup = Image.open(PHOTO_CLOSEUP)
    overview = Image.open(PHOTO_OVERVIEW)
    fig = plt.figure(figsize=(15.0, 5.3))
    grid = fig.add_gridspec(1, 3, width_ratios=[1.05, 1.30, 1.0])
    ax1 = fig.add_subplot(grid[0, 0])
    ax2 = fig.add_subplot(grid[0, 1])
    ax3 = fig.add_subplot(grid[0, 2])
    ax1.imshow(closeup)
    ax1.set_title("(a) STM32F103 platform close-up", fontsize=10)
    ax1.axis("off")
    ax2.imshow(overview)
    ax2.set_title("(b) Representative wiring overview", fontsize=10)
    ax2.axis("off")

    names = ["A0", "A1", "A2", "A3"]
    log_values = [np.log10(np.asarray(cycles[name], dtype=float)) for name in names]
    box = ax3.boxplot(
        log_values,
        tick_labels=names,
        showfliers=False,
        patch_artist=True,
        medianprops={"color": "black", "lw": 1.2},
    )
    for patch, name in zip(box["boxes"], names):
        patch.set_facecolor(mpl_colors.to_rgba(ALGORITHM_COLORS[name], 0.45))
        patch.set_edgecolor(ALGORITHM_COLORS[name])
    rng = np.random.default_rng(20260803)
    for position, name, values in zip(range(1, 5), names, log_values):
        sample_count = min(220, len(values))
        indices = rng.choice(len(values), size=sample_count, replace=False)
        jitter = rng.uniform(-0.14, 0.14, size=sample_count)
        ax3.scatter(position + jitter, values[indices], s=5,
                    color=ALGORITHM_COLORS[name], alpha=0.25, linewidth=0)
    ax3.axhline(np.log10(72_000), color="#d62728", ls="--", lw=1.1,
                label="72,000 cycles")
    ax3.set_ylabel("log10(block-maximum cycles)")
    ax3.set_title("(c) Physical DWT cycle distribution", fontsize=10)
    ax3.grid(axis="y", alpha=0.25)
    ax3.legend(frameon=False, fontsize=8, loc="upper left")
    ax3.text(
        0.98,
        0.02,
        "36 cold starts; 160 blocks/run",
        transform=ax3.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color="#555555",
    )
    fig.suptitle("Physical STM32 evidence and measured cycle distributions",
                 fontweight="bold", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    files = save_figure(fig, "fig6_physical_platform_and_dwt_cycles")
    return files, {
        "figure_id": "Fig6",
        "function": "Document the physical setup and the measured DWT cycle distribution.",
        "sources": [
            str(PHOTO_CLOSEUP.relative_to(ROOT)),
            str(PHOTO_OVERVIEW.relative_to(ROOT)),
            "outputs/phase5_physical_core/logs/*.txt",
        ],
        "transformation": (
            "User-provided JPEGs placed unchanged in a multi-panel layout; cycle panel "
            "uses all positive per-block maximum-cycle records from 36 logs."
        ),
        "rights_state": "USER_PROVIDED_AUTHORSHIP_CONFIRMATION_REQUIRED",
        "first_citation": "Implementation results: physical platform and DWT timing",
    }


def generate_tables() -> tuple[list[Path], list[dict[str, Any]]]:
    algorithm = pd.read_csv(ALGORITHM_CSV)
    physical = pd.read_csv(PHYSICAL_MATRIX_CSV)
    resource = pd.read_csv(PHYSICAL_RESOURCE_CSV)

    table1_rows = [
        {"section": "signal", "item": "sample_rate_hz", "value": "1000", "provenance": "protocol v0.3.0"},
        {"section": "signal", "item": "samples_per_run", "value": "8000", "provenance": "protocol v0.3.0"},
        {"section": "signal", "item": "duration_s", "value": "8", "provenance": "protocol v0.3.0"},
        {"section": "signal", "item": "block_size_samples", "value": "50", "provenance": "phase3 freeze"},
        {"section": "main_matrix", "item": "algorithms", "value": "A0,A1,A2,A3", "provenance": "protocol v0.3.0"},
        {"section": "main_matrix", "item": "frequency_trajectories", "value": "F0-F5", "provenance": "protocol v0.3.0"},
        {"section": "main_matrix", "item": "pli_amplitudes", "value": "0.20,0.50,1.00", "provenance": "protocol v0.3.0"},
        {"section": "main_matrix", "item": "noise_levels", "value": "none,20 dB,10 dB", "provenance": "protocol v0.3.0"},
        {"section": "main_matrix", "item": "frozen_test_seeds", "value": "1000-1029", "provenance": "phase4 completion manifest"},
        {"section": "main_matrix", "item": "run_count", "value": "6480", "provenance": "phase4 completion manifest"},
        {"section": "near_line", "item": "cases", "value": "N0,N1(42Hz),N2(58Hz),N3(42+58Hz)", "provenance": "protocol v0.3.0"},
        {"section": "near_line", "item": "run_count", "value": "1440", "provenance": "phase4 completion manifest"},
        {"section": "ablation", "item": "run_count", "value": "360", "provenance": "phase3 freeze"},
        {"section": "physical", "item": "matrix", "value": "12 scenarios x 3 cold starts", "provenance": "phase5 validation"},
    ]
    write_csv(TABLE1_CSV, table1_rows)

    table2_rows: list[dict[str, Any]] = []
    for _, row in algorithm.iterrows():
        table2_rows.append({
            "algorithm": row["algorithm"],
            "n": int(row["n"]),
            "output_snr_mean_db": row["output_snr_db_mean"],
            "output_snr_sd_db": row["output_snr_db_sd"],
            "output_snr_median_db": row["output_snr_db_median"],
            "rmse_mean": row["rmse_mean"],
            "frequency_mae_mean_hz": row["frequency_mae_hz_mean"],
            "frequency_p95_error_mean_hz": row["frequency_p95_abs_error_hz_mean"],
            "tracker_calls_mean": row["tracker_calls_mean"],
            "tracker_calls_median": row["tracker_calls_median"],
            "state_fast_fraction_mean": row["state_fast_fraction_mean"],
            "state_mid_fraction_mean": row["state_mid_fraction_mean"],
            "state_slow_fraction_mean": row["state_slow_fraction_mean"],
        })
    write_csv(TABLE2_CSV, table2_rows)

    merged = physical.merge(resource, on=["scenario_id", "algorithm", "trajectory", "pli_amplitude"])
    table3_rows: list[dict[str, Any]] = []
    for algorithm_name, subset in merged.groupby("algorithm", sort=True):
        table3_rows.append({
            "algorithm": algorithm_name,
            "scenario_count": int(len(subset)),
            "cycles_mean_across_scenarios": float(subset["cycles_mean"].mean()),
            "cycles_mean_min": int(subset["cycles_mean"].min()),
            "cycles_mean_max": int(subset["cycles_mean"].max()),
            "cycles_p95_max": int(subset["cycles_p95"].max()),
            "cycles_observed_max": int(subset["cycles_max"].max()),
            "tracker_calls_mean": float(subset["final_tracker_calls"].mean()),
            "rom_bytes_min": int(subset["rom_bytes"].min()),
            "rom_bytes_max": int(subset["rom_bytes"].max()),
            "rw_bytes_min": int(subset["rw_bytes"].min()),
            "rw_bytes_max": int(subset["rw_bytes"].max()),
            "realtime_pass_scenarios": int((subset["realtime_status"] == "PASS").sum()),
            "resource_boundary": "whole unified firmware image, not isolated algorithm footprint",
        })
    write_csv(TABLE3_CSV, table3_rows)

    table_records = [
        {
            "table_id": "Table1",
            "function": "Protocol parameters and data partitions.",
            "path": str(TABLE1_CSV.relative_to(ROOT)),
            "sources": ["protocol v0.3.0", "phase3 freeze", "phase4/5 manifests"],
            "rights_state": "ORIGINAL_PROJECT_DATA",
            "first_citation": "Methods: experiment protocol",
        },
        {
            "table_id": "Table2",
            "function": "Four-algorithm frozen main-matrix results.",
            "path": str(TABLE2_CSV.relative_to(ROOT)),
            "sources": [str(ALGORITHM_CSV.relative_to(ROOT))],
            "rights_state": "ORIGINAL_PROJECT_DATA",
            "first_citation": "Results: host comparison",
        },
        {
            "table_id": "Table3",
            "function": "Physical cycles and whole-firmware Flash/RAM evidence.",
            "path": str(TABLE3_CSV.relative_to(ROOT)),
            "sources": [
                str(PHYSICAL_MATRIX_CSV.relative_to(ROOT)),
                str(PHYSICAL_RESOURCE_CSV.relative_to(ROOT)),
            ],
            "rights_state": "ORIGINAL_PROJECT_DATA",
            "first_citation": "Implementation results: STM32 resources",
        },
    ]
    return [TABLE1_CSV, TABLE2_CSV, TABLE3_CSV], table_records


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)

    required = [
        PROTOCOL,
        METRICS_CSV,
        HOLM_CSV,
        STATS_JSON,
        ALGORITHM_CSV,
        ABLATION_CSV,
        PHYSICAL_MATRIX_CSV,
        PHYSICAL_RESOURCE_CSV,
        CONSISTENCY_CSV,
        PHOTO_MANIFEST,
    ]
    photo_inputs = [PHOTO_CLOSEUP, PHOTO_OVERVIEW]
    photo_inputs_available = all(path.exists() for path in photo_inputs)
    if photo_inputs_available:
        required.extend(photo_inputs)
    trace_inputs = [
        PHASE4_DIR / "batches" / f"main_{trajectory}_P050_Z1_N0.npz"
        for trajectory in ("F1", "F2", "F5")
    ]
    trace_inputs_available = all(path.exists() for path in trace_inputs)
    if trace_inputs_available:
        required.extend(trace_inputs)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"missing figure inputs: {missing}")
    if len(list(LOG_DIR.glob("*.txt"))) != 36:
        raise RuntimeError("expected 36 physical log files")

    figure_files: list[Path] = []
    figure_records: list[dict[str, Any]] = []
    builders = [
        figure1_scheduler,
        figure3_snr_ci,
        figure4_pareto,
        figure5_ablation,
    ]
    if trace_inputs_available:
        builders.insert(1, figure2_tracking_waveforms)
    if photo_inputs_available:
        builders.append(figure6_photos_cycles)
    for builder in builders:
        files, record = builder()
        figure_files.extend(files)
        record["files"] = [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in files
        ]
        figure_records.append(record)

    if not trace_inputs_available:
        files = [
            FIG_DIR / "fig2_frequency_tracking_and_output_waveforms.png",
            FIG_DIR / "fig2_frequency_tracking_and_output_waveforms.svg",
        ]
        missing_preserved = [str(path) for path in files if not path.exists()]
        if missing_preserved:
            raise RuntimeError(
                "Phase-4 NPZ batches are not released and preserved Fig. 2 is missing: "
                f"{missing_preserved}"
            )
        figure_files.extend(files)
        figure_records.append({
            "figure_id": "Fig2",
            "function": (
                "Show representative tracking and output traces for F1/F2/F5."
            ),
            "sources": [
                "hash-locked composite preserved from the complete Phase-4 package"
            ],
            "transformation": (
                "The released package preserves the generated Fig. 2 PNG/SVG. "
                "It does not regenerate this figure because the 287 MB regenerable "
                "NPZ batch set is intentionally excluded."
            ),
            "rights_state": "ORIGINAL_PROJECT_DATA_PRESERVED",
            "first_citation": "Results: representative dynamic trajectories",
            "files": [
                {
                    "path": str(path.relative_to(ROOT)),
                    "sha256": sha256(path),
                    "bytes": path.stat().st_size,
                }
                for path in files
            ],
        })

    if not photo_inputs_available:
        files = [
            FIG_DIR / "fig6_physical_platform_and_dwt_cycles.png",
            FIG_DIR / "fig6_physical_platform_and_dwt_cycles.svg",
        ]
        missing_preserved = [str(path) for path in files if not path.exists()]
        if missing_preserved:
            raise RuntimeError(
                "raw photographs are not released and preserved Fig. 6 is missing: "
                f"{missing_preserved}"
            )
        figure_files.extend(files)
        figure_records.append({
            "figure_id": "Fig6",
            "function": (
                "Document the physical setup and the measured DWT cycle distribution."
            ),
            "sources": [
                "rights-cleared composite preserved from the manuscript package",
                "outputs/phase5_physical_core/logs/*.txt",
            ],
            "transformation": (
                "The released package preserves the rights-cleared Fig. 6 PNG/SVG. "
                "It does not regenerate the photo panels because the raw photographs "
                "are outside the authorized public package."
            ),
            "rights_state": "RIGHTS_CLEARED_COMPOSITE_PRESERVED",
            "first_citation": (
                "Implementation results: physical platform and DWT timing"
            ),
            "files": [
                {
                    "path": str(path.relative_to(ROOT)),
                    "sha256": sha256(path),
                    "bytes": path.stat().st_size,
                }
                for path in files
            ],
        })

    figure_records.sort(key=lambda record: int(record["figure_id"][3:]))

    table_files, table_records = generate_tables()
    for record in table_records:
        path = ROOT / record["path"]
        record["sha256"] = sha256(path)
        record["bytes"] = path.stat().st_size

    input_records = [
        {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)}
        for path in required
    ]
    log_hashes = [
        {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)}
        for path in sorted(LOG_DIR.glob("*.txt"))
    ]
    manifest = {
        "schema_version": "1.0.0",
        "status": (
            "PASS_WITH_HUMAN_RIGHTS_CHECK"
            if photo_inputs_available
            else "PASS_WITH_PRESERVED_RIGHTS_CLEARED_FIG6"
        ),
        "script": {
            "path": str(Path(__file__).resolve().relative_to(ROOT)),
            "sha256": sha256(Path(__file__).resolve()),
        },
        "inputs": input_records,
        "physical_log_count": len(log_hashes),
        "physical_log_hashes": log_hashes,
        "figures": figure_records,
        "tables": table_records,
        "checks": {
            "six_figures_png_and_svg": "PASS",
            "three_candidate_tables": "PASS",
            "figure_data_sources_hash_bound": "PASS",
            "figure2_trace_batches": (
                "PASS" if trace_inputs_available else "PRESERVED_OUTPUT"
            ),
            "physical_log_count_36": "PASS",
            "photo_original_bytes_preserved": (
                "PASS" if photo_inputs_available else "NOT_INCLUDED"
            ),
            "photo_authorship_and_publication_consent": (
                "HUMAN_REVIEW_REQUIRED"
                if photo_inputs_available
                else "RIGHTS_CONFIRMED_OUTSIDE_PUBLIC_PACKAGE"
            ),
            "hard_realtime_claim_boundary_visible": "PASS",
        },
        "frozen_hash_assertions": {
            "protocol_sha256": sha256(PROTOCOL),
            "ei_draft_sha256": NONPUBLIC_EI_DRAFT_SHA256,
            "ei_draft_verification": "NOT_CHECKED_FILE_NOT_PUBLIC",
        },
    }
    MANIFEST_JSON.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": manifest["status"],
        "figure_count": len(figure_records),
        "figure_file_count": len(figure_files),
        "table_count": len(table_files),
        "manifest": {
            "path": str(MANIFEST_JSON.relative_to(ROOT)),
            "sha256": sha256(MANIFEST_JSON),
            "bytes": MANIFEST_JSON.stat().st_size,
        },
        "checks": manifest["checks"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
