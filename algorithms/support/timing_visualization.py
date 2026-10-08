"""Readable, source-backed timing explanation; changes presentation only."""
from pathlib import Path
import numpy as np


def timing_figure(model, data, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    tau = float(model['candidate_tau_ms'])
    low = float(model['student_t_95_low_ms'])
    high = float(model['student_t_95_high_ms'])
    leader = 'Camera' if tau < 0 else 'Livox' if tau > 0 else None
    follower = 'Livox' if tau < 0 else 'camera'
    magnitude = abs(tau)
    dark, muted = '#203b47', '#576b75'
    teal, orange = '#15766e', '#c7722f'
    with plt.rc_context({'font.family': 'DejaVu Sans', 'font.size': 12,
                         'axes.labelcolor': dark, 'text.color': dark,
                         'xtick.color': muted, 'ytick.color': muted}):
        fig = plt.figure(figsize=(12, 8.4), facecolor='white')
        headline_amount = f'{magnitude:.0f}' if magnitude >= 1 else f'{magnitude:.3f}'
        title = (f'{leader} content leads {follower} by about {headline_amount} ms'
                 if leader else 'No timing separation in the fitted model')
        fig.text(.055, .952, title, size=22, weight='bold')
        fig.text(.055, .918,
                 f'Model estimate on bag-record time  |  {model["bags"]} recordings',
                 size=12, color=muted)

        # Step 1: translate the saved sign convention into a matching-scene example.
        fig.text(.055, .861, '1  What does the estimated delay mean?', size=15, weight='bold')
        fig.text(.055, .792, f'{magnitude:.2f} ms', size=31, weight='bold', color=teal)
        if low <= 0 <= high:
            interval = f'Signed delay 95% interval: [{low:+.2f}, {high:+.2f}] ms'
        else:
            bounds = sorted((abs(low), abs(high)))
            interval = f'Conditional 95% interval: {bounds[0]:.2f}–{bounds[1]:.2f} ms'
        fig.text(.055, .751, interval, size=11)
        fig.text(.055, .716, f'Standard error: {model["standard_error_ms"]:.3f} ms',
                 size=11, color=muted)
        fig.text(.055, .681, f'Signed model delay τ = {tau:+.2f} ms', size=11, color=muted)
        if low <= 0 <= high:
            fig.text(.055, .647, 'The interval includes zero; lead direction is uncertain.', size=10, color=muted)

        timeline = fig.add_axes([.48, .674, .465, .156])
        timeline.set_ylim(-.75, 1.5)
        timeline.axis('off')
        extent = max(magnitude, 10.)
        x0, x1 = min(0., -tau), max(0., -tau)
        timeline.set_xlim(x0 - extent * .44, x1 + extent * .43)
        timeline.text(.5, 1.22, 'One matching flywheel scene · timestamp example',
                      transform=timeline.transAxes, ha='center', size=10, color=muted)
        for y, name, x, color in ((1., 'Camera', 0., teal), (0., 'Livox Avia', -tau, orange)):
            timeline.plot([x0 - extent * .02, x1 + extent * .04], [y, y],
                          color='#d5dde1', lw=2, zorder=1)
            timeline.scatter([x], [y], s=110, color=color, zorder=3)
            timeline.text(x0 - extent * .13, y, name, ha='right', va='center',
                          color=color, weight='bold', size=11)
            timeline.text(x, y + .22, f'{1 + x / 1000:.6f} s',
                          ha='center', va='bottom', color=color, size=11)
            timeline.plot([x, x], [-.27, y], color=color, lw=1, ls=':', alpha=.7)
        if magnitude:
            timeline.annotate('', xy=(x1, -.27), xytext=(x0, -.27),
                              arrowprops={'arrowstyle': '<->', 'color': dark, 'lw': 1.5})
            timeline.text((x0+x1)/2, -.65, f'{magnitude:.2f} ms apart', ha='center', size=10)

        # Step 2: remove the fitted setup intercepts for display, keeping all observations.
        fig.text(.055, .606, '2  How do the recordings support this estimate?', size=15, weight='bold')
        fig.text(.055, .574, 'Fixed mounting / setup phase is removed below, so both setups share one line.',
                 size=11, color=muted)
        ax = fig.add_axes([.095, .193, .84, .33])
        rpm = np.asarray(data['omega_deg_s']) / 6.
        phase = np.asarray(data['phase_unwrapped_deg'])
        groups = np.asarray(data['group_index'])
        colors = ('#2d79a6', '#c7722f', '#7a8038', '#ad5f86', '#7560a1')
        markers = ('o', '^', 's', 'D', 'P', 'v', 'X')
        adjusted = np.empty_like(phase)
        for i, group in enumerate(model['groups']):
            keep = groups == i
            adjusted[keep] = phase[keep] - model['group_phase_intercepts_deg'][group]
            ax.scatter(rpm[keep], adjusted[keep], s=65, color=colors[i % len(colors)],
                       marker=markers[i % len(markers)], edgecolors='white', lw=.8,
                       label=f'Setup {i+1} ({group})', zorder=4)
        width = max(float(np.max(np.abs(rpm))), 1.)
        grid = np.linspace(-width * 1.09, width * 1.09, 200)
        ax.plot(grid, 6 * grid * tau / 1000., color=dark, lw=2,
                label='Shared fitted delay', zorder=2)
        ax.axhline(0, color='#9cabb2', lw=.9)
        ax.axvline(0, color='#9cabb2', lw=.9)
        ax.grid(axis='y', color='#e6eaed', lw=.8)
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
        for side in ('left', 'bottom'): ax.spines[side].set_color('#bac6cc')
        ax.set(xlabel='Rotation speed (signed RPM)',
               ylabel='Remaining angle gap (°)\nLivox − camera')
        ax.legend(loc='upper left', bbox_to_anchor=(0, 1.14), borderaxespad=0,
                  fontsize=10, frameon=False, ncol=3)
        example_rpm = min(10., width)
        gap = 6 * example_rpm * tau / 1000.
        example = (f'{leader} is ~{abs(gap):.2f}° ahead\n(modeled, after setup correction)'
                   if leader else 'Modeled angle gap = 0°')
        ax.annotate(f'At +{example_rpm:g} RPM\n{example}',
                    xy=(example_rpm, gap), xytext=(.61, .84 if tau <= 0 else .31), textcoords='axes fraction',
                    fontsize=10, ha='left', va='top',
                    bbox={'facecolor': 'white', 'edgecolor': 'none', 'pad': 4},
                    arrowprops={'arrowstyle': '->', 'color': muted, 'lw': 1.2})
        fig.text(.095, .112, 'Each dot = one recording; nearby dots can overlap. + / − RPM indicates direction.',
                 size=11, color=muted)
        fig.text(.095, .079, f'Angle gap = 6 × signed RPM × τ (seconds). Phase-fit residual STD: '
                 f'{model["phase_residual_std_deg"]:.3f}°.', size=10, color=muted)
        fig.text(.055, .037, 'Physical exposure and per-ray timing remain uncalibrated; '
                 'the interval does not account for unknown systematic bias.', size=10, color=muted)
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=160, facecolor='white')
        plt.close(fig)
